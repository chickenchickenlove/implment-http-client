import asyncio
from asyncio.streams import StreamReader, StreamWriter

class ClientReader:

    MAX_BYTES_TO_READ = 4096

    def __init__(self, reader: StreamReader):
        self.reader = reader

    def transfer_raw_headers_to_dict(self, raw_headers: str) -> dict[str, str]:
        result = {}
        for header in raw_headers.split('\r\n')[:-1]:
            name, content = header.split(': ')
            result[name] = content
        return result

    async def _read_body(self, headers: dict[str, str]):
        if 'Content-Length' in headers.keys():
            length = int(headers.get('Content-Length'))
            return await self._read_body_generally(length)

        return await self._read_body_generally(0)

    async def _read_body_generally(self, length: int):

        unread_bytes = length
        msg = b''

        while not self.reader.at_eof():
            try:
                this_time_read = min(unread_bytes, ClientReader.MAX_BYTES_TO_READ)

                # To prevent abuser with Aggressive content-length.
                coro = self.reader.read(this_time_read)
                msg += await asyncio.wait_for(coro, timeout=1)

                unread_bytes -= this_time_read
                if unread_bytes <= 0:
                    self.reader.feed_eof()
            except asyncio.TimeoutError:
                print('Timeout occurred.')
            finally:
                self.reader.feed_eof()

        return msg

    async def read_message(self):
        http_method, uri, http_version = await self._read_determine_http_scheme()
        raw_headers = await self._read_headers_from_message()
        headers = self.transfer_raw_headers_to_dict(raw_headers)

        body = await self._read_body(headers)
        msg_dict = {
            'method': http_method,
            'uri': uri,
            'http_version': http_version,
            'headers': headers,
            'body': body
        }
        return msg_dict

    async def _read_determine_http_scheme(self):
        http_method, uri, http_version = (await self.reader.readline()).decode().split(' ')
        return http_method, uri, http_version

    async def _read_headers_from_message(self) -> str:
        b'POST / HTTP/1.1\r\nHost: localhost:8080\r\nUser-Agent: curl/8.9.1\r\nAccept: */*\r\nHELLO: 1\r\nBALLO: 2\r\nContent-Length: 15\r\nContent-Type: application/x-www-form-urlencoded\r\n\r\n123123123123123'
        b'GET / HTTP/1.1\r\nHost: localhost:8080\r\nUser-Agent: curl/8.9.1\r\nAccept: */*\r\nHELLO: 1\r\nBALLO: 2\r\n\r\n'
        msg = b''
        while (read_msg := (await self.reader.readline())) != b'\r\n':
            msg += read_msg
        return msg.decode()

    async def _read_chunk_message(self, extra_msg):
        raise NotImplementedError()
