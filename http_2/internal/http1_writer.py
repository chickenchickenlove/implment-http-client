from abc import abstractmethod
from asyncio.streams import StreamWriter
from typing import cast

from http_2.internal.interface_response import Response
from http_2.internal.http1_response import Http1StreamingResponse, Http1Response
from http_2.public.writer import AbstractHttp1ResponseWriter

# Chunked encoding 헤더에는 Transfer-Encoding: chunked가 표시되고, 본문은 chunk size+내용+chunk size+내용... 형식으로 표시된다.
# Transfer-Encoding = chunked

class Http1ResponseWriter(AbstractHttp1ResponseWriter):

    def __init__(self, writer: StreamWriter):
        self._writer = writer

    async def write(self, response: Response):
        await self._write_status_line(response)
        await self._write_header_lines(response)
        await self._write_body(response)

    async def _write_status_line(self, response: Response):
        http_protocol = response.protocol
        status_code = response.status_code.status_code
        status_code_text = response.status_code.text

        status_line = ' '.join(map(lambda x: str(x), [http_protocol, status_code, status_code_text])) + '\r\n'
        encoded_status_line = status_line.encode()
        self._writer.write(encoded_status_line)
        await self._writer.drain()

    async def _write_header_lines(self, response: Response):
        header_lines = ''

        for header_key, header_value in response.headers.items():
            header_line = f'{header_key}: {header_value}\r\n'
            header_lines += header_line

        header_lines += '\r\n'
        encoded_header_lines = header_lines.encode()
        self._writer.write(encoded_header_lines)
        await self._writer.drain()

    @abstractmethod
    async def _write_body(self, response: Response):
        pass

    def get_extra_info(self, key: str):
        if hasattr(self, '_writer'):
            writer = getattr(self, '_writer')
            writer = cast(StreamWriter, writer)
            return writer.transport.get_extra_info(key)
        return None


class GeneralHttp1ResponseWriter(Http1ResponseWriter):

    def __init__(self, writer: StreamWriter):
        super().__init__(writer)
        self._writer: StreamWriter = writer

    async def write(self, response: Http1Response):
        await self._write_status_line(response)
        await self._write_header_lines(response)
        await self._write_body(response)

    async def _write_status_line(self, response: Http1Response):
        await super()._write_status_line(response)

    async def _write_header_lines(self, response: Http1Response):
        await super()._write_header_lines(response)

    async def _write_body(self, response: Http1Response):
        encoded_body = response.body.encode('utf-8') if response.body else b'\r\n'
        self._writer.write(encoded_body)
        await self._writer.drain()

    async def wait_closed(self):
        self._writer.close()
        await self._writer.wait_closed()


class ChunkedResponseWriter(Http1ResponseWriter):

    def __init__(self, writer: StreamWriter):
        super().__init__(writer)
        self._writer = writer

    async def write(self, http_response: Http1StreamingResponse):
        await self._write_status_line(http_response)
        await self._write_header_lines(http_response)
        await self._write_body(http_response)

    async def _write_status_line(self, response: Http1StreamingResponse):
        await super()._write_status_line(response)

    async def _write_header_lines(self, response: Http1StreamingResponse):
        await super()._write_header_lines(response)

    async def _write_body(self, response: Http1StreamingResponse):
        while True:
            body = await response.next_response()
            body = str(body)
            if not body:
                self._writer.write(b'0\r\n\r\n')
                await self._writer.drain()
                break

            encoded_body = body.encode()
            # Chunk size should be hex type. note -> :x
            encoded_length = f"{len(encoded_body):x}".encode(response.encoding)
            self._writer.write(encoded_length + b'\r\n' + encoded_body + b'\r\n')
            await self._writer.drain()
