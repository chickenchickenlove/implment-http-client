import asyncio

from typing import Callable, Literal
from asyncio.streams import StreamReader, StreamWriter
from hyperframe.frame import Frame

from http_2.context import HTTP1ConnectionContext, HTTP1RequestContext
from http_2.protocol_change import ProtocolChange
from http_2.client_reader import Http1Reader
from http_2.public.expect_continue_exception import NeedResponseToClientRightAwayException
from http_2.exception import NeedToChangeProtocolException

from http_2.internal.http1_request import Http1Request
from http_2.internal.writer_selector import Http1ResponseWriterSelector


async def send_frame(client_writer: StreamWriter, frame: Frame):
    client_writer.write(frame.serialize())
    await client_writer.drain()


class Http1Connection:

    def __init__(self, reader: StreamReader, writer: StreamWriter, first_line_msg: bytes):

        self._reader = Http1Reader(reader)
        self._writer = writer
        self.msg = first_line_msg
        self._should_keep_alive = True
        self._should_read_body = False


    async def _maybe_protocol_upgrade(self, http_request: Http1Request):
        headers = http_request.headers
        # https://datatracker.ietf.org/doc/html/rfc7540#section-3.2
        #  Connection: Upgrade, HTTP2-Settings
        #  Upgrade: h2c
        #  HTTP2-Settings: <base64url encoding of HTTP/2 SETTINGS payload>
        if 'connection' in headers.keys():
            connection_header = headers.get('connection', '')
            upgrade_header = headers.get('upgrade', '')
            http2_settings_header = headers.get('http2-settings', '')
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

    def _update_keep_alive(self,
                           protocol: Literal['HTTP/1.1', 'HTTP/1.0'],
                           headers: dict[str, str]) -> None:
        match protocol:
            case 'HTTP/1':
                if headers.get('connection') and headers.get('connection') == 'keep-alive':
                    self._should_keep_alive = True
            case 'HTTP/1.1':
                if headers.get('connection') and headers.get('connection') == 'close':
                    self._should_keep_alive = False
            case _:
                raise NotImplemented(f'Unexpected protocol. {protocol}')

    def _update_contents_length(self, headers: dict[str, str]) -> None:
        if 'content-length' in headers.keys():
            content_len = int(headers['content-length'])
            self._should_read_body = content_len > 0

    async def handle_request(self, dispatch: Callable) -> None:
        connection_ctx = HTTP1ConnectionContext(self)
        previous_data_from_buffer = self.msg
        while True:
            if not self._should_keep_alive:
                break

            # Sometimes, Clients ignores 417 response and it may send a body.
            # In that case, this method will throw error and close connection. (Bad Request as well)
            http_method, uri, protocol = await self._reader.read_request_line(previous_data_from_buffer)
            previous_data_from_buffer = b''
            headers = await self._reader.read_header_lines()

            # Base on Headers, we can determine keep-alive and body.
            self._update_keep_alive(protocol, headers)
            self._update_contents_length(headers)

            http_request = Http1Request(http_method, uri, protocol, headers)

            if http_request.expect_100_continue():
                try:
                    http_request.execute_chains_100_continue()
                except NeedResponseToClientRightAwayException as e:
                    # TODO: Catch Exception and write response -> Response and continue
                    raise e

            if self._should_read_body:
                http_request.body = await self._reader.read_body_lines(headers)
                self._should_read_body = False

            request_ctx = HTTP1RequestContext(http_request)

            await self._maybe_protocol_upgrade(http_request)
            res = await dispatch(connection_ctx, request_ctx)

            await Http1ResponseWriterSelector.write(res, self._writer)
