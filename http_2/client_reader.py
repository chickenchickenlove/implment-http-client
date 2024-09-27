import asyncio

from asyncio.streams import StreamReader
from abc import ABC, abstractmethod
from typing import Tuple, Literal

from http_2.type.http_object import HeaderType
from http_2.exception import MaybeClientCloseConnectionOrBadRequestException
from http_2.exception import RequestTimeoutException
from http_2.exception import InvalidRequestBodyException


class HttpReader(ABC):

    @abstractmethod
    async def read_request_line(self, previous_data_from_buffer: bytes) -> Tuple[str, str, Literal['HTTP/1.1', 'HTTP/1.0']]:
        pass

    @abstractmethod
    async def read_header_lines(self) -> HeaderType:
        pass

    @abstractmethod
    async def read_body_lines(self, headers: HeaderType) -> str:
        pass

    @abstractmethod
    async def should_read_body(self) -> bool:
        pass


class Http1Reader(HttpReader):

    MAX_BYTES_TO_READ = 4096

    def __init__(self, reader: StreamReader):
        self._reader = reader
        self._should_read_body = False

    async def read_request_line(self,
                                previous_data_from_buffer: bytes
                                ) -> Tuple[str, str, Literal['HTTP/1.1', 'HTTP/1.0']]:

        def strip_useless_enter(x: str):
            return x.rstrip('\r\n')

        if previous_data_from_buffer:
            data = previous_data_from_buffer
        else:
            try:
                # Clients may open TCP connection and they don't send any request over HTTP.
                # In that case, server will keep connection forever.
                # However, it can be a weak point, because abuser can use it.
                # Thus, we should book cancel schedule with timeout.
                coro = self._reader.readline()
                data = await asyncio.wait_for(coro, timeout=1)
            except asyncio.TimeoutError:
                raise MaybeClientCloseConnectionOrBadRequestException('Failed to read request line because of timeout.')

        data = data.decode().rstrip('\r\n')

        try:
            http_method, uri, protocol = map(strip_useless_enter, data.split(' '))
            return http_method, uri, protocol
        except Exception:
            raise MaybeClientCloseConnectionOrBadRequestException('The client might close connection first.')
        pass

    async def read_header_lines(self) -> HeaderType:
        msg = b''
        while True:
            # Clients may open TCP connection and they don't send any request over HTTP.
            # In that case, server will keep connection forever.
            # However, it can be a weak point, because abuser can use it.
            # Thus, we should book cancel schedule with timeout.
            try:
                coro = self._reader.readline()
                read_msg = await asyncio.wait_for(coro, timeout=1)
            except asyncio.TimeoutError:
                raise RequestTimeoutException('Failed to read header lines because of timeout.')

            if read_msg == b'\r\n':
                break
            msg += read_msg

        raw_headers = msg.decode()

        return self._convert_headers_dict(raw_headers)

    def _convert_headers_dict(self, raw_headers: str) -> HeaderType:
        result = {}
        for header in raw_headers.split('\r\n')[:-1]:
            name, content = header.split(': ')
            result[name.lower()] = content
        return result

    async def read_body_lines(self, headers: HeaderType) -> str:
        if 'content-length' in headers.keys():
            length = int(headers.get('content-length'))
            byte_body = await self._read_body_generally(length)
            # https://datatracker.ietf.org/doc/html/rfc7230#section-3.3.3
            # Note 3.3.3-4
            # field-values or a single Content-Length header field having an invalid value,
            # then the message framing is invalid and the recipient MUST treat it as an
            # unrecoverable error.  If this is a request message, the server MUST respond with a 400 (Bad Request)
            # status code and then close the connection.
            if length != len(byte_body):
                raise InvalidRequestBodyException(
                    f'Client indicate that content-length is {length}, but actual body length is {len(byte_body)}')
            return byte_body.decode()

        byte_body = await self._read_body_generally(0)
        return byte_body.decode()

    async def _read_body_generally(self, length: int) -> bytes:

        unread_bytes = length
        msg = b''

        while unread_bytes:
            try:
                this_time_read = min(unread_bytes, Http1Reader.MAX_BYTES_TO_READ)

                # To prevent abuser with Aggressive content-length.
                coro = self._reader.read(this_time_read)
                msg += await asyncio.wait_for(coro, timeout=1)

                unread_bytes -= this_time_read
            except asyncio.TimeoutError:
                raise RequestTimeoutException(
                    'Server wait to read body, but client may send a partial body or no body at all.')
            finally:
                self._reader.feed_eof()

        return msg

    def should_read_body(self):
        return self._should_read_body
