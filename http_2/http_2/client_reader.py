import asyncio
from asyncio.streams import StreamReader, StreamWriter
from generic_http_object import Http1Response, Http2Response

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

    async def read(self, length: int):
        return await self.reader.read(length)

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
        http_method, uri, http_version = await self._read_determine_http_scheme(previous_data_from_buffer)
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

    async def _read_determine_http_scheme(self, previous_data_from_buffer:bytes):
        def strip_useless_enter(x: str):
            return x.rstrip('\r\n')
        if previous_data_from_buffer:
            http_method, uri, http_version = map(strip_useless_enter, previous_data_from_buffer.decode().rstrip('\r\n').split(' '))
        else:
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
                 writer: StreamWriter):
        self.writer: StreamWriter = writer

    async def write(self, http_response: Http1Response, http_version: str):
        response_byte = self.make_response_bytes(http_response, http_version)
        self.writer.write(response_byte)
        await self.writer.drain()

    def get_extra_info(self, key: str):
        return self.writer.transport.get_extra_info(key)

    async def wait_closed(self):
        self.writer.close()
        await self.writer.wait_closed()

    def make_response_bytes(self, http_response: Http1Response, http_version: str):

        http_protocol = http_version
        status_code = http_response.status_code.status_code
        status_code_text = http_response.status_code.text

        status_line = ' '.join(map(lambda x: str(x), [http_protocol, status_code, status_code_text]))

        response = ResponseConverter()
        response.append_status(status_line)
        for key, value in http_response.headers.items():
            response.append_header_line(f'{key}: {value}')

        response.append_body_line(http_response.body)
        return response.to_byte()

'''
# HTTP Response Msg format. 
# Case: 1 (/wo Body)
HTTP/1.1 200 OK      # Status Line
Content-Length: 0    # HEADERS LINE
                     # EMPTY LINE
# Case: 2 (/w Body)
HTTP/1.1 200 OK      # STATUS LINE
Content-Length: 4    # HEADERS LINE
                     # EMPTY LINE
body                 # BODY LINE
'''


class ResponseConverter:

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
        self.headers_line.append(f'Content-Type: text/plain')

        if data:
            self.data.append(data)
        else :
            self.data.append('')

    def to_byte(self):
        return '\r\n'.join([
            *self.status_line,
            *self.headers_line,
            '',
            *self.data]).encode()
