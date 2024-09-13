import asyncio

import hyperframe.frame

from protocol_parser import verify_protocol

from asyncio.streams import StreamReader, StreamWriter
from hyperframe.frame import Frame, SettingsFrame, PriorityFrame, HeadersFrame, DataFrame, PushPromiseFrame, PingFrame, WindowUpdateFrame, GoAwayFrame, ContinuationFrame, RstStreamFrame, ExtensionFrame
from hpack import Decoder, Encoder, HPACKDecodingError

from error_code import StreamErrorCode
from http2_error import Http2ConnectionError

from typing import Self, Union, Optional

from flags import END_STREAM, END_HEADERS, ACK
from interface import Http2ConnectionInterface
from http2_object import Http2Stream, Http2StreamQueue, Http2Settings
from frame_handler import HANDLER_STORE

from http2_exception import SettingsValueException
from utils import GeneratorWrapper

async def send_frame(client_writer: StreamWriter, frame: Frame):
    client_writer.write(frame.serialize())
    await client_writer.drain()

class HttpRequest:

    def __init__(self, stream: Http2Stream):
        self.headers = stream.headers
        self.body = stream.body
        self.method = stream.headers.get('method')
        self.host = stream.headers.get('host')
        self.protocol = stream.headers.get('protocol')
        self.path = stream.headers.get('path')
        self.stream = stream

async def aiter(q: asyncio.Queue):
    while True:
        yield await q.get()

class Http2Connection:

    FRAME_HEADER_LENGTH = 9

    @classmethod
    async def create(cls, reader: StreamReader, writer: StreamWriter) -> Self:
        await Http2Connection.send_settings_frame(writer)
        return Http2Connection(writer, reader)


    @staticmethod
    async def read_frame(reader: StreamReader, writer: StreamWriter) -> (Frame, int):

        frame_header = await reader.read(Http2Connection.FRAME_HEADER_LENGTH)

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

    def __init__(self, writer: StreamWriter, reader: StreamReader):

        # for managing stream.
        self.settings = Http2Settings()
        self.streams_que = Http2StreamQueue()

        self.writer = writer
        self.reader = reader
        self.decoder = Decoder()
        self.encode = Encoder()

        self.window_update_subscriber: dict[int, asyncio.Queue] = {}

        self.last_stream_id = 0
        self.last_frame: Union[None, HeadersFrame, DataFrame, ContinuationFrame] = None

    # This method is for stopping all async generator by sending message 'TERMINATE'
    def _get_all_async_generator(self) -> list[asyncio.Queue]:
        result = [self.streams_que.streams]
        for subscriber in self.window_update_subscriber.values():
            result.append(subscriber)
        return result

    async def publish_end(self) -> None:
        await self.streams_que.publish_end()
        for async_generator in self.window_update_subscriber.values():
            await async_generator.put(GeneratorWrapper.TERM_SIGNAL)

    def update_setting(self, frame: SettingsFrame) -> None:
        self.settings.update_settings(frame)


    async def has_any_violation(self, frame):
        if frame.stream_id > 0 and (frame.stream_id % 2) == 0:
            await self.break_out_frame(0, StreamErrorCode.PROTOCOL_ERROR)
            return True

        if frame.stream_id > 0 and self.settings.max_concurrent_streams() < self.streams_que.total_qsize() + 1:
            print('MAX REFUSED CONCURRENT STREAM VIOLATION')
            await self.break_out_frame(0, StreamErrorCode.REFUSED_STREAM)
            return True

        if self.last_frame and frame.stream_id > 0 and self.last_frame.stream_id > frame.stream_id:
            await self.break_out_frame(0, StreamErrorCode.PROTOCOL_ERROR)
            return True

        return False

    async def parse_http2_frame(self):

        connection_callbacks = Http2ConnectionInterface(
            update_window_size=self.update_window_size,
            update_setting=self.update_setting,
            cancel_stream=self.cancel_stream,
            break_out_frame=self.break_out_frame,
            update_stream=self.update_stream,
            completed_partial_stream=self.completed_partial_stream,
            has_been_done=self.has_been_done,
            find_stream=self.find_stream,
            publish_window_update=self.publish_window_update,
            remove_stream_by_force=self.remove_stream_by_force
        )

        while True:
            try:
                frame, body_length = await Http2Connection.read_frame(self.reader, self.writer)
                frame = await Http2Connection.read_frame_body(self.reader, frame, body_length)

                if await self.has_any_violation(frame):
                    continue

                if isinstance(frame, SettingsFrame):
                    handler = HANDLER_STORE.get_handler(frame)
                    await handler.handle(frame, self.reader, self.writer, connection_callbacks, self.decoder, self.streams_que, self.settings)

                if isinstance(frame, HeadersFrame):
                    handler = HANDLER_STORE.get_handler(frame)
                    await handler.handle(frame, self.reader, self.writer, connection_callbacks, self.decoder, self.streams_que, self.settings)

                # HTTP/2 프로토콜에 따르면, 헤더 블록이 여러 프레임에 걸쳐 전송될 때, HEADERS 프레임과 CONTINUATION 프레임은 연속적으로 전송되어야 합니다. 즉, 헤더 블록이 완전히 전송되기 전까지는 다른 스트림에 대한 프레임을 포함하여 다른 유형의 프레임이 전송되어서는 안 됩니다.
                if isinstance(frame, ContinuationFrame):
                    stream_id = frame.stream_id

                    if not self.streams_que.is_in_receiving(stream_id):
                    # if (stream_id not in self.streams_in_receiving.keys()):
                        self.cancel_stream(stream_id)
                        await self.break_out_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR)

                    if frame.stream_id > 0 and self.last_frame.stream_id > frame.stream_id:
                        self.cancel_stream(stream_id)
                        await self.break_out_frame(0, StreamErrorCode.PROTOCOL_ERROR)
                        continue

                    if self.has_been_done(stream_id):
                        self.cancel_stream(stream_id)
                        await self.break_out_frame(stream_id, StreamErrorCode.STREAM_CLOSED)
                        continue

                    data = frame.data
                    stream = self.find_stream(stream_id, frame)

                    if stream.header_status == Http2Stream.DONE:
                        self.cancel_stream(stream_id)
                        await self.break_out_frame(stream_id, StreamErrorCode.STREAM_CLOSED)
                        continue

                    if not((isinstance(self.last_frame, HeadersFrame) or isinstance(self.last_frame, ContinuationFrame)) and self.last_frame.stream_id == stream_id):
                        self.cancel_stream(stream_id)
                        await self.break_out_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR)
                        continue

                    if self.settings.max_frame_size() < len(data):
                        self.cancel_stream(stream_id)
                        await self.break_out_frame(stream_id, StreamErrorCode.FRAME_SIZE_ERROR)
                        continue

                    stream.update_raw_headers(frame.data)

                    if END_HEADERS in frame.flags:
                        try:
                            decoded_headers = self.decoder.decode(stream.raw_headers)
                        except HPACKDecodingError as e:
                            await self.break_out_frame(0, StreamErrorCode.COMPRESSION_ERROR)
                        else:
                            stream.update_headers_new(decoded_headers)
                            stream.complete_headers()

                    self.update_stream(stream_id, stream)
                    if stream.stream_status == Http2Stream.DONE and stream.header_status == Http2Stream.DONE:
                        await self.completed_partial_stream(stream_id, stream)

                if isinstance(frame, DataFrame):
                    handler = HANDLER_STORE.get_handler(frame)
                    await handler.handle(frame, self.reader, self.writer, connection_callbacks, self.decoder, self.streams_que, self.settings)

                if isinstance(frame, PingFrame):
                    handler = HANDLER_STORE.get_handler(frame)
                    await handler.handle(frame, self.reader, self.writer, connection_callbacks, self.decoder, self.streams_que, self.settings)

                if isinstance(frame, PriorityFrame):
                    handler = HANDLER_STORE.get_handler(frame)
                    await handler.handle(frame, self.reader, self.writer, connection_callbacks, self.decoder, self.streams_que, self.settings)

                if isinstance(frame, WindowUpdateFrame):
                    handler = HANDLER_STORE.get_handler(frame)
                    await handler.handle(frame, self.reader, self.writer, connection_callbacks, self.decoder, self.streams_que, self.settings)

                if isinstance(frame, RstStreamFrame):
                    handler = HANDLER_STORE.get_handler(frame)
                    await handler.handle(frame, self.reader, self.writer, connection_callbacks, self.decoder, self.streams_que, self.settings)

                if isinstance(frame, ExtensionFrame):
                    stream_id = frame.stream_id
                    stream = self.find_stream(stream_id, frame)

                    if stream and (stream.stream_status != Http2Stream.INIT or stream.header_status != Http2Stream.INIT):
                        self.cancel_stream(stream_id)
                        await self.break_out_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR)
                        continue

                    if self.last_frame:
                        last_stream = self.find_stream(self.last_frame.stream_id, self.last_frame)
                        if last_stream and (last_stream.stream_status != Http2Stream.INIT or last_stream.header_status != Http2Stream.INIT):
                            self.cancel_stream(stream_id)
                            await self.break_out_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR)
                            continue

                if isinstance(frame, (HeadersFrame, DataFrame)):
                    self.last_frame = frame
                # print(frame)
            except asyncio.TimeoutError:
                print('No need to read buffer.')
                break
            except hyperframe.frame.InvalidDataError as e:
                print(e)
                if isinstance(frame, SettingsFrame):
                    await self.break_out_frame(0, StreamErrorCode.FRAME_SIZE_ERROR)
                else:
                    await self.break_out_frame(0, StreamErrorCode.PROTOCOL_ERROR)
                continue
            except hyperframe.frame.InvalidPaddingError as e:
                print(e)
                await self.break_out_frame(0, StreamErrorCode.PROTOCOL_ERROR)
                continue
            except hyperframe.frame.InvalidFrameError as e:
                print(e)
                await self.break_out_frame(0, StreamErrorCode.FRAME_SIZE_ERROR)
                continue
            except SettingsValueException as e:
                print(e)
                stream_id = e.response_frame.stream_id
                if stream_id and stream_id > 0:
                    self.cancel_stream(stream_id)
                self.writer.write(e.response_frame.serialize())
                await self.writer.drain()
                continue
            except ConnectionResetError as e:
                print(f'Client reset connection first.')
                break
            except asyncio.CancelledError as e:
                print('MY CORUTINE CANCELED', e)
            except Exception as e:
                print("MY EXCEPTION", e)
                break
                # await self.publish_end()

        await self.publish_end()

    async def publish_window_update(self):
        for v in self.window_update_subscriber.values():
            q: asyncio.Queue = v
            await q.put(1)

    def update_window_size(self, frame: Frame):

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

    def cancel_stream(self, stream_id: int):
        if stream_id in self.streams_que.get_streams_in_que().keys():
            self.streams_que.cancel_stream(stream_id)

    async def consume_complete_stream(self):
        try:
            async for completed_stream in GeneratorWrapper(self.streams_que.get_streams()):
                stream_id = completed_stream.stream_id
                if self.streams_que.is_canceled_stream(stream_id):
                    continue

                http_request = HttpRequest(completed_stream)

                self.last_stream_id = completed_stream.stream_id

                self.streams_que.maybe_completed_que_overflows()

                await self.dummy_response(http_request, self.writer)
                self.streams_que.add_completed_stream(stream_id)

        except asyncio.CancelledError as e:
            loop = asyncio.get_running_loop()
            print("consume_complete_stream was cancelled")
            raise
        except RuntimeError as e:
            print(e)
        except Exception as e:
            print(e)
            print('consume_complete_stream')

    def remove_stream_by_force(self, stream_id):
        if self.streams_que.is_in_receiving(stream_id):
            self.streams_que.remove_stream_from_receiving(stream_id)

    def has_been_done(self, stream_id):
        return self.streams_que.has_been_done(stream_id)

    async def break_out_frame(self, stream_id, reason: StreamErrorCode):
        self.remove_stream_by_force(stream_id)
        frame = GoAwayFrame(stream_id=0, last_stream_id=self.last_stream_id, error_code=reason.code)
        self.writer.write(frame.serialize())
        await self.writer.drain()

    async def dummy_response(self, http_request: HttpRequest, writer: StreamWriter):

        response_headers = [
            (':status', '200'),
            ('content-type', 'text/plain-text'),
        ]

        encoder = Encoder()
        encoded_headers = encoder.encode(response_headers)

        # Header Frame does not care about window remain.
        response_headers_frame = HeadersFrame(stream_id=http_request.stream.stream_id)  # 요청과 동일한 stream_id 사용
        response_headers_frame.data = encoded_headers
        response_headers_frame.flags.add('END_HEADERS')
        writer.write(response_headers_frame.serialize())
        await writer.drain()
        # response_headers_frame.flags.add('END_STREAM')

        # 2. 응답 DATA 프레임 생성 (응답 본문 데이터)
        response_body = b"1"
        response_data_frame = DataFrame(stream_id=http_request.stream.stream_id)  # 요청과 동일한 stream_id 사용
        response_data_frame.data = response_body
        response_data_frame.flags.add('END_STREAM')
        data_size = len(response_data_frame.data)

        if http_request.stream.client_remain_window < data_size:
            print(f'SHOULD WAIT. {self.settings.get_client_connection_window()}, {http_request.stream.client_remain_window}')
            async for _ in GeneratorWrapper(http_request.stream.subscriber):
                if http_request.stream.client_remain_window >= data_size:
                    break
        print('WAIT END')
        self.settings.reduce_connection_window(data_size)
        writer.write(response_data_frame.serialize())
        await writer.drain()
        del self.window_update_subscriber[http_request.stream.stream_id]

    def subscribe(self, stream_id: int, que: asyncio.Queue) -> None:
        self.window_update_subscriber[stream_id] = que

    def find_stream(self, stream_id, frame: Frame) -> Optional[Http2Stream]:
        if not (isinstance(frame, (RstStreamFrame, SettingsFrame, WindowUpdateFrame, ExtensionFrame))) and \
                not self.streams_que.is_in_receiving(stream_id):
            new_stream = Http2Stream(stream_id, self.settings.get_client_connection_window())
            self.streams_que.add_new_stream_in_receiving(stream_id, new_stream)
            self.subscribe(stream_id, new_stream.subscriber)

        if self.streams_que.is_in_receiving(stream_id):
            return self.streams_que.find_stream_in_receiving(stream_id)

        if self.streams_que.is_in_processing(stream_id):
            return self.streams_que.find_stream_in_processing(stream_id)

        return None

    async def completed_partial_stream(self, stream_id: int, stream: Http2Stream):
        self.streams_que.remove_stream_from_receiving(stream_id)
        stream.complete_stream()
        await self.streams_que.add_new_stream_in_processing(stream_id, stream)

    def update_stream(self, stream_id: int, stream: Http2Stream):
        # stream.update()
        self.streams_que.update_stream_in_receiving(stream_id, stream)


async def execute(client_reader: StreamReader, client_writer: StreamWriter):
    global CNT

    connection = await Http2Connection.create(client_reader, client_writer)
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(connection.parse_http2_frame())
            tg.create_task(connection.consume_complete_stream())
    except Exception as e:
        print('heheheheheh')


async def handle_request(client_reader: StreamReader, client_writer: StreamWriter):
    try:
        is_valid_http2 = await verify_protocol(client_reader)
        if is_valid_http2:
            await execute(client_reader, client_writer)
        else:
            # https://datatracker.ietf.org/doc/html/rfc9113#name-error-codes
            frame = GoAwayFrame(error_code=1)
            client_writer.write(frame.serialize())
            await client_writer.drain()
    except Exception as e:
        print(f'handle request exception: {e}')
    finally:
        try:
            client_writer.close()
            await client_writer.wait_closed()
        except BrokenPipeError as e:
            print(f'Client already closed connection.')
        except ConnectionResetError as e:
            print(f'Client already closed connection.')
        except Exception as e:
            print(e)
        except asyncio.CancelledError:
            # If client
            print('here10101010')




async def main():
    http_server = await asyncio.start_server(handle_request, '127.0.0.1', 8080)
    async with http_server:
        await asyncio.gather(http_server.serve_forever())


if __name__ == '__main__':
    asyncio.run(main())


# 헤더 -> Continuation -> DATA 형태로 와야함.
# 헤더 -> DATA -> 헤더 형식으로 오려면 trailering 형태여야 함.
