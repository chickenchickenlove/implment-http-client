import logging
from asyncio.streams import StreamReader, StreamWriter
from hyperframe.frame import Frame, SettingsFrame, PriorityFrame, HeadersFrame, DataFrame, PushPromiseFrame, PingFrame, WindowUpdateFrame, GoAwayFrame, ContinuationFrame, RstStreamFrame, ExtensionFrame
from abc import ABC
from typing import Type, Dict
from hpack import Decoder, HPACKDecodingError


from http_2.interface import ConnectionInterface
from http_2.error_code import StreamErrorCode
from http_2.http2_exception import StopNextException, StopConnectionException
from http_2.http2_object import Http2Stream, Http2StreamQueue, Http2Settings
from http_2.flags import END_STREAM, END_HEADERS


class FrameHandler(ABC):

    async def handle(self,
                     frame: Frame,
                     reader: StreamReader,
                     writer: StreamWriter,
                     connection: ConnectionInterface,
                     decoder: Decoder,
                     streams_que: Http2StreamQueue,
                     settings: Http2Settings):

        try:
            await self.validate(frame, reader, writer, connection, decoder, streams_que, settings)
        except StopNextException:
            return

        try:
            await self.process(frame, reader, writer, connection, decoder, streams_que, settings)
        except StopNextException:
            return

        await self.maybe_ack(frame, reader, writer, connection, decoder, streams_que, settings)

    async def validate(self,
                       frame: Frame,
                       reader: StreamReader,
                       writer: StreamWriter,
                       connection: ConnectionInterface,
                       decoder: Decoder,
                       streams_que: Http2StreamQueue,
                       settings: Http2Settings):
        pass

    async def maybe_ack(self,
                        frame: Frame,
                        reader: StreamReader,
                        writer: StreamWriter,
                        connection: ConnectionInterface,
                        decoder: Decoder,
                        streams_que: Http2StreamQueue,
                        settings: Http2Settings):
        pass

    async def process(self,
                      frame: Frame,
                      reader: StreamReader,
                      writer: StreamWriter,
                      connection: ConnectionInterface,
                      decoder: Decoder,
                      streams_que: Http2StreamQueue,
                      settings: Http2Settings):
        pass


class SettingsFrameHandler(FrameHandler):

    # override
    async def maybe_ack(self,
                        frame: SettingsFrame,
                        reader: StreamReader,
                        writer: StreamWriter,
                        connection: ConnectionInterface,
                        decoder: Decoder,
                        streams_que: Http2StreamQueue,
                        settings: Http2Settings):
        if 'ACK' not in frame.flags:
            ack_frame = SettingsFrame(flags=['ACK'])
            writer.write(ack_frame.serialize())
            await writer.drain()

    # override
    async def process(self,
                      frame: SettingsFrame,
                      reader: StreamReader,
                      writer: StreamWriter,
                      connection: ConnectionInterface,
                      decoder: Decoder,
                      streams_que: Http2StreamQueue,
                      settings: Http2Settings):
        if 'ACK' not in frame.flags:
            await connection.update_window_size(frame)
            await connection.update_setting(frame)


class PriorityFrameHandler(FrameHandler):

    # override
    async def validate(self,
                       frame: PriorityFrame,
                       reader: StreamReader,
                       writer: StreamWriter,
                       connection: ConnectionInterface,
                       decoder: Decoder,
                       streams_que: Http2StreamQueue,
                       settings: Http2Settings):
        stream_id = frame.stream_id

        if stream_id == frame.depends_on:
            connection.cancel_stream(stream_id)
            await connection.send_goaway_frame(0, StreamErrorCode.PROTOCOL_ERROR)
            return

        if streams_que.is_in_open(stream_id):
            connection.cancel_stream(stream_id)
            await connection.send_goaway_frame(0, StreamErrorCode.PROTOCOL_ERROR)
            return


class PingFrameHandler(FrameHandler):

    # override
    async def validate(self,
                       frame: PingFrame,
                       reader: StreamReader,
                       writer: StreamWriter,
                       connection: ConnectionInterface,
                       decoder: Decoder,
                       streams_que: Http2StreamQueue,
                       settings: Http2Settings):
        """
        We don't need to validate whether PingFrame is wrong.
        Because it's determined when hyperframe parse the frame body.
        """
        pass

    # override
    async def maybe_ack(self,
                        frame: PingFrame,
                        reader: StreamReader,
                        writer: StreamWriter,
                        connection: ConnectionInterface,
                        decoder: Decoder,
                        streams_que: Http2StreamQueue,
                        settings: Http2Settings):
        if 'ACK' in frame.flags:
            return
        ack_frame = PingFrame(flags=['ACK'], stream_id=frame.stream_id, opaque_data=frame.opaque_data)
        writer.write(ack_frame.serialize())
        await writer.drain()


class RstStreamFrameHandler(FrameHandler):

    # override
    async def validate(self,
                       frame: RstStreamFrame,
                       reader: StreamReader,
                       writer: StreamWriter,
                       connection: ConnectionInterface,
                       decoder: Decoder,
                       streams_que: Http2StreamQueue,
                       settings: Http2Settings):
        stream_id = frame.stream_id

        if not connection.find_stream(stream_id, frame):
            connection.cancel_stream(stream_id)
            await connection.send_goaway_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR)
            raise StopNextException()

    # override
    async def process(self,
                      frame: RstStreamFrame,
                      reader: StreamReader,
                      writer: StreamWriter,
                      connection: ConnectionInterface,
                      decoder: Decoder,
                      streams_que: Http2StreamQueue,
                      settings: Http2Settings):
        stream_id = frame.stream_id
        stream = connection.find_stream(stream_id, frame)

        # https://datatracker.ietf.org/doc/html/rfc9113#section-5.1-7.14.1
        # A stream enters the "closed" state after an endpoint both sends and
        # receives a frame with an END_STREAM flag set. A stream also enters the "closed" state
        # after an endpoint either sends or receives a RST_STREAM frame.
        if stream:
            stream.close_state()

        connection.remove_stream_by_force(stream_id)
        await connection.send_goaway_frame(stream_id, StreamErrorCode.STREAM_CLOSED)


class HeadersFrameHandler(FrameHandler):

    # override
    async def validate(self,
                       frame: HeadersFrame,
                       reader: StreamReader,
                       writer: StreamWriter,
                       connection: ConnectionInterface,
                       decoder: Decoder,
                       streams_que: Http2StreamQueue,
                       settings: Http2Settings):

        stream_id = frame.stream_id
        data = frame.data

        if stream_id == frame.depends_on:
            connection.cancel_stream(stream_id)
            await connection.send_goaway_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR)
            raise StopNextException()

        if connection.has_been_closed(stream_id):
            connection.cancel_stream(stream_id)
            await connection.send_goaway_frame(stream_id, StreamErrorCode.STREAM_CLOSED)
            raise StopNextException()

        stream = connection.find_stream(stream_id, frame)

        ok, error_code = stream.is_allowed_frame(frame)
        if not ok:
            connection.cancel_stream(stream_id)
            await connection.send_goaway_frame(stream_id, error_code)
            raise StopNextException()

        # Invalid case
        if stream.header_status == Http2Stream.DONE and END_STREAM not in frame.flags:
            connection.cancel_stream(stream_id)
            await connection.send_goaway_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR)
            raise StopNextException()

        if settings.max_frame_size() < len(data):
            connection.cancel_stream(stream_id)
            await connection.send_goaway_frame(stream_id, StreamErrorCode.FRAME_SIZE_ERROR)
            raise StopNextException()

    # override
    async def process(self,
                      frame: HeadersFrame,
                      reader: StreamReader,
                      writer: StreamWriter,
                      connection: ConnectionInterface,
                      decoder: Decoder,
                      streams_que: Http2StreamQueue,
                      settings: Http2Settings):

        stream_id = frame.stream_id
        data = frame.data

        stream = connection.find_stream(stream_id, frame)
        stream.update_raw_headers(data)

        if END_STREAM in frame.flags:
            stream.complete_stream()

        if END_HEADERS in frame.flags:
            try:
                decoded_headers = decoder.decode(stream.raw_headers)
            except HPACKDecodingError as e:
                await connection.send_goaway_frame(0, StreamErrorCode.COMPRESSION_ERROR)
                raise StopNextException()
            else:
                stream.update_headers_new(decoded_headers)
                stream.complete_headers()

        connection.update_stream(stream_id, stream)
        if stream.stream_status == Http2Stream.DONE and stream.header_status == Http2Stream.DONE:
            await connection.completed_partial_stream(stream_id, stream)


class ContinuationFrameHandler(FrameHandler):

    # override
    async def validate(self,
                       frame: ContinuationFrame,
                       reader: StreamReader,
                       writer: StreamWriter,
                       connection: ConnectionInterface,
                       decoder: Decoder,
                       streams_que: Http2StreamQueue,
                       settings: Http2Settings):

        stream_id = frame.stream_id

        if not streams_que.is_in_open(stream_id):
            connection.cancel_stream(stream_id)
            await connection.send_goaway_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR)
            raise StopNextException()

        if frame.stream_id > 0 and connection.get_last_frame().stream_id > frame.stream_id:
            connection.cancel_stream(stream_id)
            await connection.send_goaway_frame(0, StreamErrorCode.PROTOCOL_ERROR)
            raise StopNextException()

        if connection.has_been_closed(stream_id):
            connection.cancel_stream(stream_id)
            await connection.send_goaway_frame(stream_id, StreamErrorCode.STREAM_CLOSED)
            raise StopNextException()

        data = frame.data
        stream = connection.find_stream(stream_id, frame)
        ok, error_code = stream.is_allowed_frame(frame)

        if not ok:
            connection.cancel_stream(stream_id)
            await connection.send_goaway_frame(stream_id, error_code)
            raise StopNextException()

        if not (isinstance(connection.get_last_frame(), (HeadersFrame, ContinuationFrame)) and connection.get_last_frame().stream_id == stream_id):
            connection.cancel_stream(stream_id)
            await connection.send_goaway_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR)
            raise StopNextException()

        if settings.max_frame_size() < len(data):
            connection.cancel_stream(stream_id)
            await connection.send_goaway_frame(stream_id, StreamErrorCode.FRAME_SIZE_ERROR)
            raise StopNextException()

    # override
    async def process(self,
                      frame: ContinuationFrame,
                      reader: StreamReader,
                      writer: StreamWriter,
                      connection: ConnectionInterface,
                      decoder: Decoder,
                      streams_que: Http2StreamQueue,
                      settings: Http2Settings):

        stream_id = frame.stream_id
        stream = connection.find_stream(stream_id, frame)

        data = frame.data
        stream.update_raw_headers(data)

        if END_HEADERS in frame.flags:
            try:
                decoded_headers = decoder.decode(stream.raw_headers)
            except HPACKDecodingError as e:
                logging.info(f'failed to decode ContinuationFrame: {stream.raw_headers}. exception : {e}')
                await connection.send_goaway_frame(0, StreamErrorCode.COMPRESSION_ERROR)
                raise StopNextException()
            else:
                stream.update_headers_new(decoded_headers)
                stream.complete_headers()

        connection.update_stream(stream_id, stream)
        if stream.stream_status == Http2Stream.DONE and stream.header_status == Http2Stream.DONE:
            await connection.completed_partial_stream(stream_id, stream)


class DataFrameHandler(FrameHandler):

    # override
    async def validate(self,
                       frame: DataFrame,
                       reader: StreamReader,
                       writer: StreamWriter,
                       connection: ConnectionInterface,
                       decoder: Decoder,
                       streams_que: Http2StreamQueue,
                       settings: Http2Settings):

        stream_id = frame.stream_id
        stream = connection.find_stream(stream_id, frame)
        data = frame.data

        if connection.has_been_closed(stream_id):
            connection.cancel_stream(stream_id)
            await connection.send_goaway_frame(stream_id, StreamErrorCode.STREAM_CLOSED)
            raise StopNextException()

        if stream.header_status != Http2Stream.DONE:
            connection.cancel_stream(stream_id)
            await connection.send_goaway_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR)
            raise StopNextException()

        if stream.stream_status == Http2Stream.DONE:
            connection.cancel_stream(stream_id)
            await connection.send_goaway_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR)
            raise StopNextException()

        if settings.max_frame_size() < len(data):
            connection.cancel_stream(stream_id)
            await connection.send_goaway_frame(stream_id, StreamErrorCode.FRAME_SIZE_ERROR)
            raise StopNextException()

        ok, error_code = stream.is_allowed_frame(frame)
        if not ok:
            await connection.send_goaway_frame(stream_id, error_code)
            raise StopNextException()

    # override
    async def process(self,
                      frame: DataFrame,
                      reader: StreamReader,
                      writer: StreamWriter,
                      connection: ConnectionInterface,
                      decoder: Decoder,
                      streams_que: Http2StreamQueue,
                      settings: Http2Settings):

        stream_id = frame.stream_id
        stream = connection.find_stream(stream_id, frame)
        data = frame.data

        stream.update_raw_body(data)
        if END_STREAM in frame.flags:
            await connection.completed_partial_stream(stream_id, stream)
        else:
            stream.update()
        connection.update_stream(stream_id, stream)


class ExtensionFrameHandler(FrameHandler):

    # override
    async def validate(self,
                       frame: ExtensionFrame,
                       reader: StreamReader,
                       writer: StreamWriter,
                       connection: ConnectionInterface,
                       decoder: Decoder,
                       streams_que: Http2StreamQueue,
                       settings: Http2Settings):

        stream_id = frame.stream_id
        stream = connection.find_stream(stream_id, frame)

        if stream and (stream.stream_status != Http2Stream.INIT or stream.header_status != Http2Stream.INIT):
            connection.cancel_stream(stream_id)
            await connection.send_goaway_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR)
            raise StopNextException()

    # override
    async def process(self,
                      frame: ExtensionFrame,
                      reader: StreamReader,
                      writer: StreamWriter,
                      connection: ConnectionInterface,
                      decoder: Decoder,
                      streams_que: Http2StreamQueue,
                      settings: Http2Settings):
        stream_id = frame.stream_id

        if connection.get_last_frame():
            last_frame = connection.get_last_frame()
            last_stream = connection.find_stream(last_frame.stream_id, last_frame)
            if last_stream and (last_stream.stream_status != Http2Stream.INIT or last_stream.header_status != Http2Stream.INIT):
                connection.cancel_stream(stream_id)
                await connection.send_goaway_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR)
                raise StopNextException()


class WindowUpdateFrameHandler(FrameHandler):

    # override
    async def validate(self,
                       frame: WindowUpdateFrame,
                       reader: StreamReader,
                       writer: StreamWriter,
                       connection: ConnectionInterface,
                       decoder: Decoder,
                       streams_que: Http2StreamQueue,
                       settings: Http2Settings):

        stream_id = frame.stream_id

        if stream_id > 0 and streams_que.not_existed_anywhere(stream_id):
            connection.cancel_stream(stream_id)
            await connection.send_goaway_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR)
            raise StopNextException()

    # override
    async def process(self,
                      frame: WindowUpdateFrame,
                      reader: StreamReader,
                      writer: StreamWriter,
                      connection: ConnectionInterface,
                      decoder: Decoder,
                      streams_que: Http2StreamQueue,
                      settings: Http2Settings):
        stream_id = frame.stream_id
        stream = connection.find_stream(stream_id, frame)

        # If stream_id = 0, it will affect setting of connection level.
        if stream_id == 0:
            await connection.update_window_size(frame)
        # else, it will affect setting of stream level.
        else:
            await stream.update_window(frame.window_increment)

class PushPromiseFrameHandler(FrameHandler):

    async def validate(self, frame: PushPromiseFrame, reader: StreamReader, writer: StreamWriter,
                       connection: ConnectionInterface, decoder: Decoder, streams_que: Http2StreamQueue,
                       settings: Http2Settings):
        raise NotImplementedError(f'Unexpected situation. because server never got PushPormisedFrame.')

    async def maybe_ack(self, frame: PushPromiseFrame, reader: StreamReader, writer: StreamWriter,
                        connection: ConnectionInterface, decoder: Decoder, streams_que: Http2StreamQueue,
                        settings: Http2Settings):
        raise NotImplementedError(f'Unexpected situation. because server never got PushPormisedFrame.')

    async def process(self, frame: PushPromiseFrame, reader: StreamReader, writer: StreamWriter,
                      connection: ConnectionInterface, decoder: Decoder, streams_que: Http2StreamQueue,
                      settings: Http2Settings):
        raise NotImplementedError(f'Unexpected situation. because server never got PushPormisedFrame.')


class GoawayFrameHandler(FrameHandler):

    # override
    async def validate(self,
                       frame: GoAwayFrame,
                       reader: StreamReader,
                       writer: StreamWriter,
                       connection: ConnectionInterface,
                       decoder: Decoder,
                       streams_que: Http2StreamQueue,
                       settings: Http2Settings):
        stream_id = frame.stream_id
        if stream_id != 0:
            connection.cancel_stream(stream_id)
            await connection.send_goaway_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR)
            raise StopNextException()

    async def process(self,
                      frame: GoAwayFrame,
                      reader: StreamReader,
                      writer: StreamWriter,
                      connection: ConnectionInterface,
                      decoder: Decoder,
                      streams_que: Http2StreamQueue,
                      settings: Http2Settings):
        raise StopConnectionException('Server received GoawayFrame from client. ')


class UnsupportedFrameHandler(FrameHandler):

    # override
    async def validate(self, frame: Frame, reader: StreamReader, writer: StreamWriter,
                       connection: ConnectionInterface, decoder: Decoder, streams_que: Http2StreamQueue, settings: Http2Settings):
        # https://datatracker.ietf.org/doc/html/rfc9113#name-server-push
        # A client cannot push. Thus, servers MUST treat the receipt of a PUSH_PROMISE frame
        # as a connection error (Section 5.4.1) of type PROTOCOL_ERROR.
        # A server cannot set the SETTINGS_ENABLE_PUSH setting to a value other than 0 (see Section 6.5.2).
        raise StopConnectionException('')

    # override
    async def maybe_ack(self, frame: Frame, reader: StreamReader, writer: StreamWriter,
                        connection: ConnectionInterface, decoder: Decoder, streams_que: Http2StreamQueue, settings: Http2Settings):
        raise NotImplementedError(f'No handlers for type {type(frame)}')

    # override
    async def process(self, frame: Frame, reader: StreamReader, writer: StreamWriter,
                      connection: ConnectionInterface, decoder: Decoder, streams_que: Http2StreamQueue, settings: Http2Settings):
        raise NotImplementedError(f'No handlers for type {type(frame)}')


class HandlerStore:

    DEFAULT_HANDLER = UnsupportedFrameHandler()

    def __init__(self):
        self.handler_store: Dict[Type[Frame], FrameHandler] = {
            SettingsFrame: SettingsFrameHandler(),
            PingFrame: PingFrameHandler(),
            PriorityFrame: PriorityFrameHandler(),
            RstStreamFrame: RstStreamFrameHandler(),
            HeadersFrame: HeadersFrameHandler(),
            WindowUpdateFrame: WindowUpdateFrameHandler(),
            DataFrame: DataFrameHandler(),
            ExtensionFrame: ExtensionFrameHandler(),
            ContinuationFrame: ContinuationFrameHandler(),
            GoAwayFrame: GoawayFrameHandler(),
            PushPromiseFrame: PushPromiseFrameHandler()
        }

    def get_handler(self, frame: Frame) -> FrameHandler:
        return self.handler_store.get(type(frame), HANDLER_STORE.DEFAULT_HANDLER)


HANDLER_STORE = HandlerStore()
