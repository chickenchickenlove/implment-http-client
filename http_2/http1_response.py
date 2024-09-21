from abc import abstractmethod, ABC
from asyncio.streams import StreamWriter
from typing import AsyncIterable, cast

from http_2.status_code import StatusCode

class Response(ABC):

    @property
    @abstractmethod
    def protocol(self):
        pass

    @property
    @abstractmethod
    def status_code(self):
        pass

    @property
    @abstractmethod
    def headers(self):
        pass

    @property
    @abstractmethod
    def body(self):
        pass

    @abstractmethod
    def has_body(self):
        pass


class GeneralHttp1Response(Response):

    def __init__(self,
                 status_code: StatusCode = StatusCode.OK,
                 headers: dict[str, str] | None = None,
                 body: str = ''):
        self._protocol = 'HTTP/1.1'
        self._status_code = status_code
        self._headers = {} if headers is None else headers
        self._body = body

        if body:
            header_for_body = {
                'Content-Type': 'text/plain',
                'Content-length': str(len(body))
            }
            self._headers.update(header_for_body)
        else:
            header_for_body = {
                'Content-length': '0'
            }
            self._headers.update(header_for_body)

    @property
    def protocol(self):
        return self._protocol

    @property
    def status_code(self):
        return self._status_code

    @property
    def headers(self):
        return self._headers

    @property
    def body(self):
        return self._body

    def has_body(self):
        return len(self._body) > 0


class StreamingResponse(Response):

    def __init__(self,
                 contents_generator: AsyncIterable,
                 status_code: StatusCode = StatusCode.OK,
                 headers: dict[str, str] | None = None,
                 media_type: str = 'text/event-stream',
                 char_set: str = 'utf-8'
                 ):

        self._body_iterator = contents_generator
        self._status_code = status_code
        self._headers = {} if headers is None else headers
        self._media_type = media_type
        self._char_set = char_set
        self._protocol = 'HTTP/1.1'
        self._encoding = 'utf-8'

        if media_type == 'text/event-stream':
            headers = {
                'Content-Type': 'text/event-stream',
                'Transfer-Encoding': 'chunked',
                'Cache-Control': 'no-cache'
            }
            self._headers.update(headers)

    async def next_response(self):
        async for chunk in self._body_iterator:
            return chunk
        return ''

    @property
    def protocol(self):
        return self._protocol

    @property
    def status_code(self):
        return self._status_code

    @property
    def encoding(self):
        return self._encoding

    @property
    def headers(self):
        return self._headers

    @property
    def body(self):
        raise NotImplemented('Not Implemented. because body is async generator')

    @property
    def has_body(self):
        raise NotImplemented('Not Implemented. because body is async generator')

# Chunked encoding 헤더에는 Transfer-Encoding: chunked가 표시되고, 본문은 chunk size+내용+chunk size+내용... 형식으로 표시된다.
# Trasfer-Encoding = chunked
#

class AbstractHttp1ResponseWriter(ABC):

    async def write(self, response: Response):
        await self._write_status_line(response)
        await self._write_header_lines(response)
        await self._write_body(response)

    @abstractmethod
    async def _write_status_line(self, response: Response):
        pass

    @abstractmethod
    async def _write_header_lines(self, response: Response):
        pass

    @abstractmethod
    async def _write_body(self, response: Response):
        pass

    def get_extra_info(self, key: str):
        if hasattr(self, '_writer'):
            writer = getattr(self, '_writer')
            writer = cast(StreamWriter, writer)
            return writer.transport.get_extra_info(key)
        return None


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


class GeneralResponseWriter(Http1ResponseWriter):

    def __init__(self, writer: StreamWriter):
        super().__init__(writer)
        self._writer: StreamWriter = writer

    async def write(self, response: GeneralHttp1Response):
        await self._write_status_line(response)
        await self._write_header_lines(response)
        await self._write_body(response)

    async def _write_status_line(self, response: GeneralHttp1Response):
        await super()._write_status_line(response)

    async def _write_header_lines(self, response: GeneralHttp1Response):
        await super()._write_header_lines(response)

    async def _write_body(self, response: GeneralHttp1Response):
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

    async def write(self, http_response: StreamingResponse):
        await self._write_status_line(http_response)
        await self._write_header_lines(http_response)
        await self._write_body(http_response)

    async def _write_status_line(self, response: StreamingResponse):
        await super()._write_status_line(response)

    async def _write_header_lines(self, response: StreamingResponse):
        await super()._write_header_lines(response)

    async def _write_body(self, response: StreamingResponse):
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
