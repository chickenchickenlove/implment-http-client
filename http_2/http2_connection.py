import asyncio
import hyperframe.frame

from asyncio.streams import StreamReader, StreamWriter
from hyperframe.frame import Frame, SettingsFrame, PriorityFrame, HeadersFrame, DataFrame, PushPromiseFrame, PingFrame, WindowUpdateFrame, GoAwayFrame, ContinuationFrame, RstStreamFrame, ExtensionFrame
from hpack import Decoder, Encoder
from typing import Self, Union, Optional, Callable

from http_2.exception import NeedToChangeProtocolException
from http_2.flags import END_STREAM, END_HEADERS
from http_2.interface import Http2ConnectionInterface
from http_2.error_code import StreamErrorCode
from http_2.http2_exception import Http2ConnectionError, StopConnectionException, SettingsValueException
from http_2.http2_object import Http2Stream, Http2StreamQueue, Http2Settings, AsyncGenerator, TerminateAwareAsyncioQue
from http_2.common_http_object import Http2Request, GenericHttpRequest, Http2ToGenericHttpRequestConverter, GenericHttpResponse, GenericHttpToHttp2ResponseConverter, Http2Response
from http_2.status_code import StatusCode

from frame_handler import HANDLER_STORE, HandlerStore


async def send_frame(client_writer: StreamWriter, frame: Frame):
    client_writer.write(frame.serialize())
    await client_writer.drain()


class Http2Connection:

    FRAME_HEADER_LENGTH = 9

    @classmethod
    async def create(cls,
                     reader: StreamReader,
                     writer: StreamWriter,
                     dispatch: Callable, /,
                     upgrade_obj: NeedToChangeProtocolException | None = None) -> Self:
        await Http2Connection.send_settings_frame(writer)
        return Http2Connection(writer, reader, dispatch, HANDLER_STORE, upgrade_obj)


    @staticmethod
    async def read_frame(reader: StreamReader, writer: StreamWriter) -> (Frame, int):

        read_task = asyncio.create_task(reader.read(Http2Connection.FRAME_HEADER_LENGTH))
        frame_header = await asyncio.wait_for(read_task, timeout=10)

        if len(frame_header) < Http2Connection.FRAME_HEADER_LENGTH:
            frame = GoAwayFrame(stream_id=0, error_code=StreamErrorCode.PROTOCOL_ERROR.code)
            await send_frame(writer, frame)
            raise Http2ConnectionError('len(frame_header) < Http2Connection.FRAME_HEADER_LENGTH')

        try:
            frame, length = Frame.parse_frame_header(memoryview(frame_header))
        except hyperframe.frame.InvalidDataError as e:
            frame = GoAwayFrame(stream_id=0, error_code=StreamErrorCode.PROTOCOL_ERROR.code)
            await send_frame(writer, frame)
            writer.close()
            await writer.wait_closed()
            raise Http2ConnectionError('hyperframe.frame.InvalidDataError')
        except asyncio.TimeoutError as e:
            print('There is no need to read it.')
        else:
            return frame, length

    @staticmethod
    async def read_frame_body(reader: StreamReader, frame: Frame, length:int) -> Frame:
        frame_payload = await reader.read(length)
        frame.parse_body(memoryview(frame_payload))
        return frame

    @staticmethod
    async def send_settings_frame(client_writer: StreamWriter):
        settings_frame = SettingsFrame(stream_id=0)
        settings_frame.settings = {
            SettingsFrame.MAX_CONCURRENT_STREAMS: Http2Settings.MAX_CONCURRENT_STREAMS_COUNT,
            SettingsFrame.INITIAL_WINDOW_SIZE: 65535
        }

        await send_frame(client_writer, settings_frame)

    def __init__(self,
                 writer: StreamWriter,
                 reader: StreamReader,
                 dispatch: Callable,
                 handler_store: HandlerStore,
                 /,
                 upgrade_obj: NeedToChangeProtocolException | None = None):

        # For Server.
        self.dispatch = dispatch

        # for managing stream.
        self.settings = Http2Settings()
        self.streams_que = Http2StreamQueue()

        self.writer = writer
        self.reader = reader
        self.decoder = Decoder()
        self.encoder = Encoder()

        self.window_update_subscriber: dict[int, TerminateAwareAsyncioQue] = {}

        self.last_stream_id = 0
        self.last_frame: Union[None, HeadersFrame, DataFrame, ContinuationFrame] = None
        self.handler_store = handler_store

        self._upgrade_obj: NeedToChangeProtocolException | None= upgrade_obj

    # This method is for stopping all async generator by sending message 'TERMINATE'
    def _get_all_async_generator(self) -> list[TerminateAwareAsyncioQue]:
        result = [self.streams_que.streams]
        for subscriber in self.window_update_subscriber.values():
            result.append(subscriber)
        return result

    def get_last_frame(self) -> Optional[Frame]:
        return self.last_frame

    async def publish_end(self) -> None:
        await self.streams_que.publish_end()
        for subscriber in self.window_update_subscriber.values():
            await subscriber.send_term_signal()

    async def update_setting(self, frame: SettingsFrame) -> None:
        self.settings.update_settings(frame)
        if frame.settings.get(frame.INITIAL_WINDOW_SIZE):
            await self.publish_window_update()

    async def send_rst_stream_frame(self, stream_id: int, error_code: StreamErrorCode):
        self.remove_stream_by_force(stream_id)
        frame = RstStreamFrame(stream_id=stream_id, last_stream_id=self.last_stream_id, error_code=error_code.code)
        self.writer.write(frame.serialize())
        await self.writer.drain()

    async def has_any_violation(self, frame):
        if frame.stream_id > 0 and (frame.stream_id % 2) == 0:
            await self.send_goaway_frame(0, StreamErrorCode.PROTOCOL_ERROR)
            return True

        if frame.stream_id > 0 and self.settings.max_concurrent_streams() < self.streams_que.total_qsize() + 1:
            print('MAX REFUSED CONCURRENT STREAM VIOLATION')
            await self.send_rst_stream_frame(frame.stream_id, error_code=StreamErrorCode.REFUSED_STREAM)
            return True

        if self.last_frame and frame.stream_id > 0 and self.last_frame.stream_id > frame.stream_id:
            await self.send_goaway_frame(0, StreamErrorCode.PROTOCOL_ERROR)
            return True

        return False

    async def parse_http2_frame(self):

        connection_callbacks = Http2ConnectionInterface(
            update_window_size=self.update_window_size,
            update_setting=self.update_setting,
            cancel_stream=self.cancel_stream,
            get_last_frame=self.get_last_frame,
            send_goaway_frame=self.send_goaway_frame,
            send_rst_stream_frame=self.send_rst_stream_frame,
            update_stream=self.update_stream,
            completed_partial_stream=self.completed_partial_stream,
            has_been_closed=self.has_been_closed,
            find_stream=self.find_stream,
            publish_window_update=self.publish_window_update,
            remove_stream_by_force=self.remove_stream_by_force
        )

        frame = None
        while True:
            try:

                # For supporting h2c upgrade protocol.
                if self._upgrade_obj is not None and self._upgrade_obj.has_next_frame():
                    frame = self._upgrade_obj.next_frame
                    if not self._upgrade_obj.has_next_frame():
                        self._upgrade_obj = None
                else:
                    frame, body_length = await Http2Connection.read_frame(self.reader, self.writer)
                    frame = await Http2Connection.read_frame_body(self.reader, frame, body_length)

                print(frame)
                if await self.has_any_violation(frame):
                    continue

                handler = self.handler_store.get_handler(frame)
                await handler.handle(frame, self.reader, self.writer, connection_callbacks, self.decoder, self.streams_que, self.settings)

                if isinstance(frame, (HeadersFrame, DataFrame)):
                    self.last_frame = frame
            except asyncio.TimeoutError:
                print('No need to read buffer.')
                break
            except hyperframe.frame.InvalidDataError as e:
                print(e)
                if isinstance(frame, SettingsFrame):
                    await self.send_goaway_frame(0, StreamErrorCode.FRAME_SIZE_ERROR)
                else:
                    await self.send_goaway_frame(0, StreamErrorCode.PROTOCOL_ERROR)
                continue
            except hyperframe.frame.InvalidPaddingError as e:
                print(e)
                await self.send_goaway_frame(0, StreamErrorCode.PROTOCOL_ERROR)
                continue
            except hyperframe.frame.InvalidFrameError as e:
                print(e)
                await self.send_goaway_frame(0, StreamErrorCode.FRAME_SIZE_ERROR)
                continue
            except SettingsValueException as e:
                print(e)
                stream_id = e.response_frame.stream_id
                if stream_id and stream_id > 0:
                    self.cancel_stream(stream_id)
                self.writer.write(e.response_frame.serialize())
                await self.writer.drain()
                continue
            except ConnectionResetError as _:
                print(f'Client reset connection first.')
                break
            except StopConnectionException as e:
                print(e)
                break
            except Exception as e:
                print("MY EXCEPTION", e)
                break

        await self.publish_end()

    async def publish_window_update(self):
        for v in self.window_update_subscriber.values():
            q: TerminateAwareAsyncioQue = v
            await q.put(1)

    async def update_window_size(self, frame: Frame):

        if isinstance(frame, WindowUpdateFrame):
            window_increment = frame.window_increment
            # https://datatracker.ietf.org/doc/html/rfc7540#section-6.9
            # The legal range for the increment to the flow-control window is 1 to 2^31-1 (2,147,483,647) octets.
            if not (0 < window_increment <= 2**31-1 and
                    0 < window_increment + self.settings.get_client_connection_window() <= 2**31-1):
                raise SettingsValueException(GoAwayFrame(error_code=StreamErrorCode.FLOW_CONTROL_ERROR.code))
            self.settings.add_connection_window(window_increment)

        if isinstance(frame, SettingsFrame) and frame.INITIAL_WINDOW_SIZE in frame.settings.keys():
            window_size = frame.settings.get(frame.INITIAL_WINDOW_SIZE)

            # Values above the maximum flow-control window size of 2^31-1 MUST be treated as a connection error (Section 5.4.1) of type FLOW_CONTROL_ERROR
            if not (0 <= window_size <= 2**31-1 and
                    0 <= window_size + self.settings.get_client_connection_window() <= 2**31-1):
                raise SettingsValueException(GoAwayFrame(error_code=StreamErrorCode.FLOW_CONTROL_ERROR.code))

            # https://datatracker.ietf.org/doc/html/rfc7540#section-6.9.2
            # In addition to changing the flow-control window for streams that are
            # not yet active, a SETTINGS frame can alter the initial flow-control
            # window size for streams with active flow-control windows (that is,
            # streams in the "open" or "half-closed (remote)" state).  When the
            # value of SETTINGS_INITIAL_WINDOW_SIZE changes, a receiver MUST adjust
            # the size of all stream flow-control windows that it maintains by the
            # difference between the new value and the old value.
            for stream in self.streams_que.get_streams_in_que().values():
                stream.update_window(window_size)
            self.settings.client_connection_window = window_size

        await self.publish_window_update()

    def cancel_stream(self, stream_id: int):
        if stream_id in self.streams_que.get_streams_in_que().keys():
            self.streams_que.cancel_stream(stream_id)

    async def consume_complete_stream(self):
        try:
            async for completed_stream in AsyncGenerator(self.streams_que.get_streams()):
                print(completed_stream)
                stream_id = completed_stream.stream_id
                if self.streams_que.is_canceled_stream(stream_id):
                    continue

                http2_request = Http2Request(completed_stream)
                self.last_stream_id = completed_stream.stream_id

                generic_request = Http2ToGenericHttpRequestConverter.convert(http2_request)
                generic_response = GenericHttpResponse(StatusCode.OK, {}, '')

                generic_req, generic_res = await self.dispatch(generic_request, generic_response)
                http2_response = GenericHttpToHttp2ResponseConverter.convert(generic_res)

                await self.send_response(http2_request, http2_response, self.writer)
                # await self.dummy_response(http2_request, self.writer)
                self.streams_que.add_closed_stream(stream_id)

        except asyncio.CancelledError as e:
            raise
        except RuntimeError as e:
            print(e)
        except Exception as e:
            print(e)

    def remove_stream_by_force(self, stream_id):
        if self.streams_que.is_in_open(stream_id):
            self.streams_que.remove_stream_from_open(stream_id)

    def has_been_done(self, stream_id: int) -> bool:
        return self.streams_que.has_been_closed(stream_id)

    def has_been_closed(self, stream_id: int) -> bool:
        return self.streams_que.has_been_closed(stream_id)

    async def send_goaway_frame(self, stream_id, reason: StreamErrorCode):
        self.remove_stream_by_force(stream_id)
        frame = GoAwayFrame(stream_id=0, last_stream_id=self.last_stream_id, error_code=reason.code)
        self.writer.write(frame.serialize())
        await self.writer.drain()

    async def send_response(self,
                            http_request: Http2Request,
                            http_response: Http2Response,
                            writer: StreamWriter
                            ):
        stream_id = http_request.stream.stream_id

        # Header Frame does not care about window remain. It will not included to window size.
        response_headers_frame = HeadersFrame(stream_id=stream_id)
        response_headers_frame.data = self.encoder.encode(http_response.response_headers)
        response_headers_frame.flags.add(END_HEADERS)

        if not http_response.body:
            response_headers_frame.flags.add(END_STREAM)

        writer.write(response_headers_frame.serialize())

        if http_response.body:
            response_data_frame = DataFrame(stream_id=stream_id)  # 요청과 동일한 stream_id 사용
            response_data_frame.data = http_response.body.encode()
            response_data_frame.flags.add(END_STREAM)

            data_size = len(response_data_frame.data)

            if http_request.stream.client_remain_window < data_size:
                print(f'Should wait to send response because of lack of window size.')
                async for d in AsyncGenerator(http_request.stream.subscriber):
                    if http_request.stream.client_remain_window >= data_size:
                        print(f'Window size is update. it is possible for stream to send response now.')
                        break

            self.settings.reduce_connection_window(data_size)
            writer.write(response_data_frame.serialize())
        await writer.drain()

        http_request.stream.close_state()
        del self.window_update_subscriber[http_request.stream.stream_id]

    def subscribe(self, stream_id: int, que: TerminateAwareAsyncioQue) -> None:
        self.window_update_subscriber[stream_id] = que

    def find_stream(self, stream_id, frame: Frame) -> Optional[Http2Stream]:
        if not (isinstance(frame, (RstStreamFrame, SettingsFrame, WindowUpdateFrame, ExtensionFrame))) and \
                not self.streams_que.is_in_open(stream_id):
            new_stream = Http2Stream(stream_id, self.settings.get_client_connection_window())
            self.streams_que.add_new_stream_in_open(stream_id, new_stream)
            self.subscribe(stream_id, new_stream.subscriber)

        if self.streams_que.is_in_open(stream_id):
            return self.streams_que.find_stream_in_open(stream_id)

        if self.streams_que.is_in_processing(stream_id):
            return self.streams_que.find_stream_in_processing(stream_id)

        return None

    async def completed_partial_stream(self, stream_id: int, stream: Http2Stream):
        self.streams_que.remove_stream_from_open(stream_id)
        stream.complete_stream()
        await self.streams_que.add_new_stream_in_processing(stream_id, stream)

    def update_stream(self, stream_id: int, stream: Http2Stream):
        self.streams_que.update_stream_in_open(stream_id, stream)
