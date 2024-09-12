from asyncio.streams import StreamReader, StreamWriter
from hyperframe.frame import Frame, SettingsFrame, PriorityFrame, HeadersFrame, DataFrame, PushPromiseFrame, PingFrame, WindowUpdateFrame, GoAwayFrame, ContinuationFrame, RstStreamFrame, ExtensionFrame
from interface import ConnectionInterface
from typing import Type, Dict
from error_code import StreamErrorCode


class FrameHandler:

    async def handle(self,
                     frame: Frame,
                     reader: StreamReader,
                     writer: StreamWriter,
                     connection_callbacks: ConnectionInterface):

        await self.validate(frame, reader, writer, connection_callbacks)
        await self.process(frame, reader, writer, connection_callbacks)
        await self.maybe_ack(frame, reader, writer, connection_callbacks)

    async def validate(self,
                 frame: Frame,
                 reader: StreamReader,
                 writer: StreamWriter,
                 connection_callbacks: ConnectionInterface):
        raise NotImplementedError()

    async def maybe_ack(self,
                        frame: Frame,
                        reader: StreamReader,
                        writer: StreamWriter,
                        connection_callbacks: ConnectionInterface):
        raise NotImplementedError()

    async def process(self,
                      frame: Frame,
                      reader: StreamReader,
                      writer: StreamWriter,
                      connection_callbacks: ConnectionInterface):
        raise NotImplementedError()


class SettingsFrameHandler(FrameHandler):

    async def validate(self,
                       frame: SettingsFrame,
                       reader: StreamReader,
                       writer: StreamWriter,
                       connection_callbacks: ConnectionInterface):
        pass

    async def maybe_ack(self,
                        frame: SettingsFrame,
                        reader: StreamReader,
                        writer: StreamWriter,
                        connection_callbacks: ConnectionInterface):
        if 'ACK' not in frame.flags:
            ack_frame = SettingsFrame(flags=['ACK'])
            writer.write(ack_frame.serialize())
            await writer.drain()

    async def process(self,
                      frame: SettingsFrame,
                      reader: StreamReader,
                      writer: StreamWriter,
                      connection_callbacks: ConnectionInterface):
        if 'ACK' not in frame.flags:
            connection_callbacks.update_window_size(frame)
            connection_callbacks.update_setting(frame)


class PriorityFrameHandler(FrameHandler):

    async def validate(self,
                       frame: PriorityFrame,
                       reader: StreamReader,
                       writer: StreamWriter,
                       connection_callbacks: ConnectionInterface):
        stream_id = frame.stream_id

        if stream_id == frame.depends_on:
            connection_callbacks.cancel_stream(stream_id)
            await connection_callbacks.break_out_frame(0, StreamErrorCode.PROTOCOL_ERROR)
            return

        if (
                stream_id in connection_callbacks.streams_in_receiving.keys()
        ):
            connection_callbacks.cancel_stream(stream_id)
            await connection_callbacks.break_out_frame(0, StreamErrorCode.PROTOCOL_ERROR)
            return

    async def maybe_ack(self, frame: PriorityFrame, reader: StreamReader, writer: StreamWriter,
                        connection_callbacks: ConnectionInterface):
        pass

    async def process(self, frame: PriorityFrame, reader: StreamReader, writer: StreamWriter,
                      connection_callbacks: ConnectionInterface):
        pass


class PingFrameHandler(FrameHandler):

    async def validate(self, frame: PingFrame, reader: StreamReader, writer: StreamWriter,
                       connection_callbacks: ConnectionInterface):
        """
        We don't need to validate whether PingFrame is wrong.
        Because it's determined when hyperframe parse the frame body.
        """
        pass

    async def maybe_ack(self, frame: PingFrame, reader: StreamReader, writer: StreamWriter,
                        connection_callbacks: ConnectionInterface):
        if 'ACK' in frame.flags:
            return
        ack_frame = PingFrame(flags=['ACK'], stream_id=frame.stream_id, opaque_data=frame.opaque_data)
        writer.write(ack_frame.serialize())
        await writer.drain()

    async def process(self, frame: PingFrame, reader: StreamReader, writer: StreamWriter,
                      connection_callbacks: ConnectionInterface):
        pass


class HandlerStore:

    def __init__(self):
        self.handler_store: Dict[Type[Frame], FrameHandler] = {
            SettingsFrame: SettingsFrameHandler(),
            PingFrame: PingFrameHandler(),

        }

    def get_handler(self, frame: Frame) ->FrameHandler:
        return self.handler_store.get(type(frame))


HANDLER_STORE = HandlerStore()
