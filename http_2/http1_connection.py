import asyncio

from typing import Callable
from asyncio.streams import StreamReader, StreamWriter
from hyperframe.frame import Frame

from http_2.constant.protocol import HTTP1_1
from http_2.context import HTTP1ConnectionContext, HTTP1RequestContext
from http_2.protocol_change import ProtocolChange
from http_2.client_reader import ClientReader
from http_2.exception import NeedToChangeProtocolException

from http_2.internal.http1_request import Http1Request
from http_2.internal.writer_selector import Http1ResponseWriterSelector


async def send_frame(client_writer: StreamWriter, frame: Frame):
    client_writer.write(frame.serialize())
    await client_writer.drain()


class Http1Connection:

    def __init__(self, reader: StreamReader, writer: StreamWriter, first_line_msg: bytes):

        self._reader = ClientReader(reader)
        self._writer = writer
        self.msg = first_line_msg

    def should_keep_alive(self, http_request: Http1Request):
        if http_request.protocol == HTTP1_1:
            return True
        if (http_request.protocol == 'HTTP/1' and
                http_request.headers.get('Connection') and
                http_request.headers.get('Connection') == 'keep-alive'):
            return True
        return False

    async def should_continue(self, timeout: int = 0.1) -> bytes:
        try:
            coro = self._reader.read(1)
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            return b''

    async def _maybe_protocol_upgrade(self, http_request: Http1Request):
        headers = http_request.headers
        # https://datatracker.ietf.org/doc/html/rfc7540#section-3.2
        #  Connection: Upgrade, HTTP2-Settings
        #  Upgrade: h2c
        #  HTTP2-Settings: <base64url encoding of HTTP/2 SETTINGS payload>
        if 'Connection' in headers.keys():
            connection_header = headers.get('Connection', '')
            upgrade_header = headers.get('Upgrade', '')
            http2_settings_header = headers.get('HTTP2-Settings', '')
            # If request has body, we ignores upgrade.
            if (
                    'Upgrade' in connection_header and
                    'HTTP2-Settings' in connection_header and
                    'h2c' in upgrade_header and
                    http2_settings_header and
                    not http_request.body
            ):
                raise NeedToChangeProtocolException(
                    method=http_request.method,
                    path=http_request.path,
                    headers=headers,
                    http2_settings_headers=http2_settings_header,
                    response_msg=ProtocolChange.get_response_msg(http_request, 'HTTP/2')
                )

    async def handle_request(self, dispatch: Callable) -> None:
        connection_ctx = HTTP1ConnectionContext(self)
        previous_data_from_buffer = self.msg
        while True:
            client_msg = await self._reader.read_message(previous_data_from_buffer)

            http_request = Http1Request(client_msg)

            request_ctx = HTTP1RequestContext(http_request)

            await self._maybe_protocol_upgrade(http_request)
            res = await dispatch(connection_ctx, request_ctx)

            await Http1ResponseWriterSelector.write(res, self._writer)
            if not self.should_keep_alive(http_request):
                break

            previous_data_from_buffer = await self.should_continue()
