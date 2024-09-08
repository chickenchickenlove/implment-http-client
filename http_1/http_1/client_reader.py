import asyncio
from asyncio.streams import StreamReader, StreamWriter
from request_response_object import HttpRequest, HttpResponse

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

        while unread_bytes:
            try:
                this_time_read = min(unread_bytes, ClientReader.MAX_BYTES_TO_READ)

                # To prevent abuser with Aggressive content-length.
                coro = self.reader.read(this_time_read)
                msg += await asyncio.wait_for(coro, timeout=1)

                unread_bytes -= this_time_read
            except asyncio.TimeoutError:
                print('Timeout occurred.')
            finally:
                self.reader.feed_eof()

        return msg

    async def read_message(self, previous_data_from_buffer: bytes):
        http_method, uri, http_version = await self._read_determine_http_scheme()
        http_method = previous_data_from_buffer.decode() + http_method
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
        def strip_useless_enter(x: str):
            return x.rstrip('\r\n')
        http_method, uri, http_version = map(strip_useless_enter, (await self.reader.readline()).decode().split(' '))
        return http_method, uri, http_version

    # HTTP Message Example
    # b'POST / HTTP/1.1\r\nHost: localhost:8080\r\nUser-Agent: curl/8.9.1\r\nAccept: */*\r\nHELLO: 1\r\nBALLO: 2\r\nContent-Length: 15\r\nContent-Type: application/x-www-form-urlencoded\r\n\r\n123123123123123'
    # b'GET / HTTP/1.1\r\nHost: localhost:8080\r\nUser-Agent: curl/8.9.1\r\nAccept: */*\r\nHELLO: 1\r\nBALLO: 2\r\n\r\n'
    async def _read_headers_from_message(self) -> str:
        msg = b''
        while (read_msg := (await self.reader.readline())) != b'\r\n':
            msg += read_msg
        return msg.decode()

    async def _read_chunk_message(self, extra_msg):
        raise NotImplementedError()


class ClientWriter:

    def __init__(self,
                 writer: StreamWriter,
                 http_response: HttpResponse):
        self.writer: StreamWriter = writer
        self.http_response = http_response

    async def write(self):
        response_byte = self.make_response_bytes()
        self.writer.write(response_byte)
        await self.writer.drain()

    def make_response_bytes(self):

        response = ResponseList()
        http_protocol = self.http_response.http_request.http_version
        status_code = self.http_response.status_code.status_code
        status_code_text = self.http_response.status_code.text

        status_line = (' ').join(map(lambda x: str(x), [http_protocol, status_code, status_code_text]))

        response.append_status(status_line)
        for key, value in self.http_response.headers.items():
            response.append_header_line(f'{key}: {value}')

        response.append_body_line(self.http_response.body)
        return response.to_byte()

'''
# HTTP Response Msg format. 
# Case: 1
HTTP/1.1 200 OK      # Status Line
Content-Length: 0    # HEADERS LINE
                     # EMPTY LINE
# Case: 2
HTTP/1.1 200 OK      # STATUS LINE
Content-Length: 4    # HEADERS LINE

body                 # EMPTY LINE
'''

class ResponseList:

    def __init__(self):
        self.status_line = []
        self.headers_line = []
        self.data = []

    def append_status(self, data):
        if data:
            self.status_line.append(data)

    def append_header_line(self, data):
        if data:
            self.headers_line.append(data)

    def append_body_line(self, data):
        data_length = 0 if data is None else len(data)
        self.headers_line.append(f'Content-Length: {data_length}')

        if data:
            self.data.append(data)

    def to_byte(self):
        return '\r\n'.join([
            *self.status_line,
            *self.headers_line,
            '\r\n',
            *self.data]).encode()
