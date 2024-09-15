import asyncio

from client_reader import ClientReader, ClientWriter
from typing import Callable
from asyncio.streams import StreamReader, StreamWriter
from generic_http_object import Http1Request, Http1Response


class Http1Connection:

    def __init__(self, reader: StreamReader, writer: StreamWriter, first_line_msg: bytes):

        self.reader = ClientReader(reader)
        self.writer = ClientWriter(writer)
        self.msg = first_line_msg

    def should_keep_alive(self, http_request: Http1Request):
        if http_request.http_version == 'HTTP/1.1':
            return True
        if (http_request.http_version == 'HTTP/1' and
                http_request.headers.get('Connection') and
                http_request.headers.get('Connection') == 'keep-alive'):
            return True
        return False

    async def should_continue(self, timeout: int = 0.1) -> bytes:
        try:
            coro = self.reader.read(1)
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            return b''

    async def handle_request(self, dispatch: Callable):
        previous_data_from_buffer = self.msg
        while True:
            print(f'Socket information = {self.writer.get_extra_info("socket")}')
            client_msg = await self.reader.read_message(previous_data_from_buffer)

            http_request = Http1Request(client_msg)
            http_response = Http1Response.init_http1_response()
            await dispatch(http_request, http_response)
            # http_response = await self.handle_request(http_request)

            await self.writer.write(http_response, http_request.http_version)

            previous_data_from_buffer = await self.should_continue()
            if not previous_data_from_buffer or not self.should_keep_alive(http_request):
                await self.writer.wait_closed()
                break
