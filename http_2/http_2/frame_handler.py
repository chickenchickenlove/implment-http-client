from asyncio.streams import StreamReader, StreamWriter
from hyperframe.frame import Frame, SettingsFrame, PriorityFrame, HeadersFrame, DataFrame, PushPromiseFrame, PingFrame, WindowUpdateFrame, GoAwayFrame, ContinuationFrame, RstStreamFrame, ExtensionFrame
from interface import ConnectionInterface
from typing import Type, Dict
from error_code import StreamErrorCode

from abc import ABC, abstractmethod

from hpack import Decoder, Encoder, HPACKDecodingError

from http2_object import Http2Stream, Http2StreamQueue, Http2Settings
from flags import END_STREAM, END_HEADERS

class StopNextException(Exception):
    pass



class FrameHandler(ABC):

    async def handle(self,
                     frame: Frame,
                     reader: StreamReader,
                     writer: StreamWriter,
                     connection_callbacks: ConnectionInterface,
                     decoder: Decoder,
                     streams_que: Http2StreamQueue,
                     settings: Http2Settings):

        try:
            await self.validate(frame, reader, writer, connection_callbacks, decoder, streams_que, settings)
        except StopNextException:
            return

        try:
            await self.process(frame, reader, writer, connection_callbacks, decoder, streams_que, settings)
        except StopNextException:
            return

        await self.maybe_ack(frame, reader, writer, connection_callbacks, decoder, streams_que, settings)

    @abstractmethod
    async def validate(self,
                       frame: Frame,
                       reader: StreamReader,
                       writer: StreamWriter,
                       connection_callbacks: ConnectionInterface,
                       decoder: Decoder,
                       streams_que: Http2StreamQueue,
                       settings: Http2Settings):
        raise NotImplementedError()

    @abstractmethod
    async def maybe_ack(self,
                        frame: Frame,
                        reader: StreamReader,
                        writer: StreamWriter,
                        connection_callbacks: ConnectionInterface,
                        decoder: Decoder,
                        streams_que: Http2StreamQueue,
                        settings: Http2Settings):
        raise NotImplementedError()

    @abstractmethod
    async def process(self,
                      frame: Frame,
                      reader: StreamReader,
                      writer: StreamWriter,
                      connection_callbacks: ConnectionInterface,
                      decoder: Decoder,
                      streams_que: Http2StreamQueue,
                      settings: Http2Settings):
        raise NotImplementedError()


class SettingsFrameHandler(FrameHandler):

    async def validate(self,
                       frame: SettingsFrame,
                       reader: StreamReader,
                       writer: StreamWriter,
                       connection_callbacks: ConnectionInterface,
                       decoder: Decoder,
                       streams_que: Http2StreamQueue,
                       settings: Http2Settings):
        pass

    async def maybe_ack(self,
                        frame: SettingsFrame,
                        reader: StreamReader,
                        writer: StreamWriter,
                        connection_callbacks: ConnectionInterface,
                        decoder: Decoder,
                        streams_que: Http2StreamQueue,
                        settings: Http2Settings):
        if 'ACK' not in frame.flags:
            ack_frame = SettingsFrame(flags=['ACK'])
            writer.write(ack_frame.serialize())
            await writer.drain()

    async def process(self,
                      frame: SettingsFrame,
                      reader: StreamReader,
                      writer: StreamWriter,
                      connection_callbacks: ConnectionInterface,
                      decoder: Decoder,
                      streams_que: Http2StreamQueue,
                      settings: Http2Settings):
        if 'ACK' not in frame.flags:
            connection_callbacks.update_window_size(frame)
            connection_callbacks.update_setting(frame)


class PriorityFrameHandler(FrameHandler):

    async def validate(self,
                       frame: PriorityFrame,
                       reader: StreamReader,
                       writer: StreamWriter,
                       connection_callbacks: ConnectionInterface,
                       decoder: Decoder,
                       streams_que: Http2StreamQueue,
                       settings: Http2Settings):
        stream_id = frame.stream_id

        if stream_id == frame.depends_on:
            connection_callbacks.cancel_stream(stream_id)
            await connection_callbacks.break_out_frame(0, StreamErrorCode.PROTOCOL_ERROR)
            return

        if streams_que.is_in_receiving(stream_id):
            connection_callbacks.cancel_stream(stream_id)
            await connection_callbacks.break_out_frame(0, StreamErrorCode.PROTOCOL_ERROR)
            return

    async def maybe_ack(self,
                        frame: PriorityFrame,
                        reader: StreamReader,
                        writer: StreamWriter,
                        connection_callbacks: ConnectionInterface,
                        decoder: Decoder,
                        streams_que: Http2StreamQueue,
                        settings: Http2Settings):
        pass

    async def process(self,
                      frame: PriorityFrame,
                      reader: StreamReader,
                      writer: StreamWriter,
                      connection_callbacks: ConnectionInterface,
                      decoder: Decoder,
                      streams_que: Http2StreamQueue,
                      settings: Http2Settings):
        pass


class PingFrameHandler(FrameHandler):

    async def validate(self,
                       frame: PingFrame,
                       reader: StreamReader,
                       writer: StreamWriter,
                       connection_callbacks: ConnectionInterface,
                       decoder: Decoder,
                       streams_que: Http2StreamQueue,
                       settings: Http2Settings):
        """
        We don't need to validate whether PingFrame is wrong.
        Because it's determined when hyperframe parse the frame body.
        """
        pass

    async def maybe_ack(self, frame: PingFrame, reader: StreamReader, writer: StreamWriter,
                        connection_callbacks: ConnectionInterface,decoder: Decoder, streams_que: Http2StreamQueue, settings: Http2Settings):
        if 'ACK' in frame.flags:
            return
        ack_frame = PingFrame(flags=['ACK'], stream_id=frame.stream_id, opaque_data=frame.opaque_data)
        writer.write(ack_frame.serialize())
        await writer.drain()

    async def process(self, frame: PingFrame, reader: StreamReader, writer: StreamWriter,
                      connection_callbacks: ConnectionInterface, decoder: Decoder, streams_que: Http2StreamQueue, settings: Http2Settings):
        pass


class RstStreamFrameHandler(FrameHandler):

    async def validate(self,
                       frame: RstStreamFrame,
                       reader: StreamReader,
                       writer: StreamWriter,
                       connection_callbacks: ConnectionInterface,
                       decoder: Decoder,
                       streams_que: Http2StreamQueue,
                       settings: Http2Settings):
        stream_id = frame.stream_id

        if not connection_callbacks.find_stream(stream_id, frame):
            connection_callbacks.cancel_stream(stream_id)
            await connection_callbacks.break_out_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR)
            raise StopNextException()

    async def maybe_ack(self,
                        frame: RstStreamFrame,
                        reader: StreamReader,
                        writer: StreamWriter,
                        connection_callbacks: ConnectionInterface,
                        decoder: Decoder,
                        streams_que: Http2StreamQueue,
                        settings: Http2Settings):
        pass

    async def process(self,
                      frame: RstStreamFrame,
                      reader: StreamReader,
                      writer: StreamWriter,
                      connection_callbacks: ConnectionInterface,
                      decoder: Decoder,
                      streams_que: Http2StreamQueue,
                      settings: Http2Settings):
        stream_id = frame.stream_id
        connection_callbacks.remove_stream_by_force(stream_id)
        await connection_callbacks.break_out_frame(stream_id, StreamErrorCode.STREAM_CLOSED)


class HeadersFrameHandler(FrameHandler):

    async def validate(self,
                       frame: HeadersFrame,
                       reader: StreamReader,
                       writer: StreamWriter,
                       connection_callbacks: ConnectionInterface,
                       decoder: Decoder,
                       streams_que: Http2StreamQueue,
                       settings: Http2Settings):

        stream_id = frame.stream_id
        data = frame.data

        if stream_id == frame.depends_on:
            connection_callbacks.cancel_stream(stream_id)
            await connection_callbacks.break_out_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR)
            raise StopNextException()

        if connection_callbacks.has_been_done(stream_id):
            connection_callbacks.cancel_stream(stream_id)
            await connection_callbacks.break_out_frame(stream_id, StreamErrorCode.STREAM_CLOSED)
            raise StopNextException()

        stream = connection_callbacks.find_stream(stream_id, frame)

        # Not Trailer header case. -> invalid status.
        if stream.header_status == Http2Stream.DONE and stream.stream_status == Http2Stream.DONE:
            connection_callbacks.cancel_stream(stream_id)
            await connection_callbacks.break_out_frame(stream_id, StreamErrorCode.STREAM_CLOSED)
            raise StopNextException()

        # Invalid case
        if stream.header_status == Http2Stream.DONE and END_STREAM not in frame.flags:
            connection_callbacks.cancel_stream(stream_id)
            await connection_callbacks.break_out_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR)
            raise StopNextException()

        if settings.max_frame_size() < len(data):
            connection_callbacks.cancel_stream(stream_id)
            await connection_callbacks.break_out_frame(stream_id, StreamErrorCode.FRAME_SIZE_ERROR)
            raise StopNextException()

    async def maybe_ack(self,
                        frame: HeadersFrame,
                        reader: StreamReader,
                        writer: StreamWriter,
                        connection_callbacks: ConnectionInterface,
                        decoder: Decoder,
                        streams_que: Http2StreamQueue,
                        settings: Http2Settings):
        pass

    async def process(self,
                      frame: HeadersFrame,
                      reader: StreamReader,
                      writer: StreamWriter,
                      connection_callbacks: ConnectionInterface,
                      decoder: Decoder,
                      streams_que: Http2StreamQueue,
                      settings: Http2Settings):

        stream_id = frame.stream_id
        data = frame.data

        stream = connection_callbacks.find_stream(stream_id, frame)
        stream.update_raw_headers(data)

        if END_STREAM in frame.flags:
            stream.complete_stream()

        if END_HEADERS in frame.flags:
            try:
                decoded_headers = decoder.decode(stream.raw_headers)
            except HPACKDecodingError as e:
                await connection_callbacks.break_out_frame(0, StreamErrorCode.COMPRESSION_ERROR)
                raise StopNextException()
            else:
                stream.update_headers_new(decoded_headers)
                stream.complete_headers()

        connection_callbacks.update_stream(stream_id, stream)
        if stream.stream_status == Http2Stream.DONE and stream.header_status == Http2Stream.DONE:
            await connection_callbacks.completed_partial_stream(stream_id, stream)


class ContinuationFrameHandler(FrameHandler):

    async def validate(self,
                       frame: ContinuationFrame,
                       reader: StreamReader,
                       writer: StreamWriter,
                       connection_callbacks: ConnectionInterface,
                       decoder: Decoder,
                       streams_que: Http2StreamQueue,
                       settings: Http2Settings):
        pass


    async def maybe_ack(self,
                        frame: ContinuationFrame,
                        reader: StreamReader,
                        writer: StreamWriter,
                        connection_callbacks: ConnectionInterface,
                        decoder: Decoder,
                        streams_que: Http2StreamQueue,
                        settings: Http2Settings):
        pass

    async def process(self,
                      frame: ContinuationFrame,
                      reader: StreamReader,
                      writer: StreamWriter,
                      connection_callbacks: ConnectionInterface,
                      decoder: Decoder,
                      streams_que: Http2StreamQueue,
                      settings: Http2Settings):
        pass


class DataFrameHandler(FrameHandler):

    async def validate(self,
                       frame: DataFrame,
                       reader: StreamReader,
                       writer: StreamWriter,
                       connection_callbacks: ConnectionInterface,
                       decoder: Decoder,
                       streams_que: Http2StreamQueue,
                       settings: Http2Settings):

        stream_id = frame.stream_id
        stream = connection_callbacks.find_stream(stream_id, frame)
        data = frame.data

        if connection_callbacks.has_been_done(stream_id):
            connection_callbacks.cancel_stream(stream_id)
            await connection_callbacks.break_out_frame(stream_id, StreamErrorCode.STREAM_CLOSED)
            raise StopNextException()

        if stream.header_status != Http2Stream.DONE:
            connection_callbacks.cancel_stream(stream_id)
            await connection_callbacks.break_out_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR)
            raise StopNextException()

        if stream.stream_status == Http2Stream.DONE:
            connection_callbacks.cancel_stream(stream_id)
            await connection_callbacks.break_out_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR)
            raise StopNextException()

        if settings.max_frame_size() < len(data):
            connection_callbacks.cancel_stream(stream_id)
            await connection_callbacks.break_out_frame(stream_id, StreamErrorCode.FRAME_SIZE_ERROR)
            raise StopNextException()

    async def maybe_ack(self,
                        frame: DataFrame,
                        reader: StreamReader,
                        writer: StreamWriter,
                        connection_callbacks: ConnectionInterface,
                        decoder: Decoder,
                        streams_que: Http2StreamQueue,
                        settings: Http2Settings):
        pass

    async def process(self,
                      frame: DataFrame,
                      reader: StreamReader,
                      writer: StreamWriter,
                      connection_callbacks: ConnectionInterface,
                      decoder: Decoder,
                      streams_que: Http2StreamQueue,
                      settings: Http2Settings):

        stream_id = frame.stream_id
        stream = connection_callbacks.find_stream(stream_id, frame)
        data = frame.data

        stream.body += data
        if END_STREAM in frame.flags:
            await connection_callbacks.completed_partial_stream(stream_id, stream)
        else:
            stream.update()
        connection_callbacks.update_stream(stream_id, stream)


# class ExtensionFrameHandler(FrameHandler):
#
#     async def validate(self,
#                        frame: ExtensionFrame,
#                        reader: StreamReader,
#                        writer: StreamWriter,
#                        connection_callbacks: ConnectionInterface,
#                        decoder: Decoder,
#                        streams_que: Http2StreamQueue,
#                        settings: Http2Settings):
#
#         stream_id = frame.stream_id
#         stream = connection_callbacks.find_stream(stream_id, frame)
#
#         if stream and (stream.stream_status != Http2Stream.INIT or stream.header_status != Http2Stream.INIT):
#             connection_callbacks.cancel_stream(stream_id)
#             await connection_callbacks.break_out_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR)
#             raise StopNextException()
#
#         if self.last_frame:
#             last_stream = connection_callbacks.find_stream(self.last_frame.stream_id, self.last_frame)
#             if last_stream and (last_stream.stream_status != Http2Stream.INIT or last_stream.header_status != Http2Stream.INIT):
#                 connection_callbacks.cancel_stream(stream_id)
#                 await connection_callbacks.break_out_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR)
#                 raise StopNextException()
#
#
#     async def maybe_ack(self,
#                         frame: ExtensionFrame,
#                         reader: StreamReader,
#                         writer: StreamWriter,
#                         connection_callbacks: ConnectionInterface,
#                         decoder: Decoder,
#                         streams_que: Http2StreamQueue,
#                         settings: Http2Settings):
#         pass
#
#     async def process(self,
#                       frame: ExtensionFrame,
#                       reader: StreamReader,
#                       writer: StreamWriter,
#                       connection_callbacks: ConnectionInterface,
#                       decoder: Decoder,
#                       streams_que: Http2StreamQueue,
#                       settings: Http2Settings):
#         pass


class WindowUpdateFrameHandler(FrameHandler):


    async def validate(self,
                       frame: WindowUpdateFrame,
                       reader: StreamReader,
                       writer: StreamWriter,
                       connection_callbacks: ConnectionInterface,
                       decoder: Decoder,
                       streams_que: Http2StreamQueue,
                       settings: Http2Settings):

        stream_id = frame.stream_id

        if stream_id > 0 and streams_que.not_existed_anywhere(stream_id):
            connection_callbacks.cancel_stream(stream_id)
            await connection_callbacks.break_out_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR)
            raise StopNextException()

    async def maybe_ack(self,
                        frame: WindowUpdateFrame,
                        reader: StreamReader,
                        writer: StreamWriter,
                        connection_callbacks: ConnectionInterface,
                        decoder: Decoder,
                        streams_que: Http2StreamQueue,
                        settings: Http2Settings):
        pass

    async def process(self,
                      frame: WindowUpdateFrame,
                      reader: StreamReader,
                      writer: StreamWriter,
                      connection_callbacks: ConnectionInterface,
                      decoder: Decoder,
                      streams_que: Http2StreamQueue,
                      settings: Http2Settings):
        stream_id = frame.stream_id

        # If stream_id = 0, it will affect setting of connection level.
        if stream_id == 0:
            connection_callbacks.update_window_size(frame)
        # else, it will affect setting of stream level.
        else:
            stream = connection_callbacks.find_stream(stream_id, frame)
            stream.update_window(frame.window_increment)

        await connection_callbacks.publish_window_update()


class UnsupportedFrameHandler(FrameHandler):

    async def validate(self, frame: Frame, reader: StreamReader, writer: StreamWriter,
                       connection_callbacks: ConnectionInterface, decoder: Decoder, streams_que: Http2StreamQueue, settings: Http2Settings):
        raise NotImplementedError(f'No handlers for type {type(frame)}')

    async def maybe_ack(self, frame: Frame, reader: StreamReader, writer: StreamWriter,
                        connection_callbacks: ConnectionInterface, decoder: Decoder, streams_que: Http2StreamQueue, settings: Http2Settings):
        raise NotImplementedError(f'No handlers for type {type(frame)}')

    async def process(self, frame: Frame, reader: StreamReader, writer: StreamWriter,
                      connection_callbacks: ConnectionInterface, decoder: Decoder, streams_que: Http2StreamQueue, settings: Http2Settings):
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
        }

    def get_handler(self, frame: Frame) -> FrameHandler:
        return self.handler_store.get(type(frame), HANDLER_STORE.DEFAULT_HANDLER)


HANDLER_STORE = HandlerStore()
