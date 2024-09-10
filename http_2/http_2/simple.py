import asyncio
from asyncio.streams import StreamReader, StreamWriter
from hyperframe.frame import Frame, SettingsFrame, PriorityFrame, HeadersFrame, DataFrame, PushPromiseFrame, PingFrame, WindowUpdateFrame, GoAwayFrame, ContinuationFrame
from hpack import Decoder, Encoder, HeaderTuple
from collections import deque, defaultdict

from error_code import StreamErrorCode



async def verify_protocol(client_reader: StreamReader):
    # Preface message: b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n'
    if await client_reader.readline() != b'PRI * HTTP/2.0\r\n':
        return False
    if await client_reader.readline() != b'\r\n':
        return False
    if await client_reader.readline() != b'SM\r\n':
        return False
    if await client_reader.readline() != b'\r\n':
        return False
    return True

dq = deque([])


def consume_dq():
    global dq
    while dq:
        yield dq.pop()


async def send_settings_frame(client_writer: StreamWriter):
    settings_frame = SettingsFrame(stream_id=0)
    settings_frame.settings = {
        SettingsFrame.MAX_CONCURRENT_STREAMS: 100,
        SettingsFrame.INITIAL_WINDOW_SIZE: 65535
    }

    await send_frame(client_writer, settings_frame)


async def send_frame(client_writer: StreamWriter, frame: Frame):
    client_writer.write(frame.serialize())
    await client_writer.drain()


class Http2Stream:

    INIT = 'INIT'
    UPDATING = 'UPDATING'
    DONE = 'DONE'

    def __init__(self,
                 stream_id: int,
                 init_window: int
                 ):
        self.stream_id = stream_id
        self.client_remain_window = init_window
        self.headers = {}
        self.raw_headers = b''
        self.body = b''

        self.header_status = Http2Stream.INIT
        self.stream_status = Http2Stream.INIT

    def update(self):
        self.stream_status = Http2Stream.UPDATING

    def update_headers(self, headers: dict):
        self.headers.update(headers)

    def update_raw_headers(self, raw_header: bytes):
        self.header_status = Http2Stream.UPDATING
        self.raw_headers += raw_header

    def complete_headers(self):
        self.header_status = Http2Stream.DONE

    def complete_stream(self):
        self.stream_status = Http2Stream.DONE


class HttpRequest:

    def __init__(self, stream: Http2Stream):
        self.headers = stream.headers
        self.body = stream.body
        self.method = stream.headers.get('method')
        self.host = stream.headers.get('host')
        self.protocol = stream.headers.get('protocol')
        self.path = stream.headers.get('path')
        self.stream = stream

class Http2Connection:

    def __init__(self, frame: SettingsFrame):
        self.enable_connect_protocol = frame.ENABLE_CONNECT_PROTOCOL
        self.enable_push = frame.ENABLE_PUSH
        self.header_table_size = frame.HEADER_TABLE_SIZE

        self.client_connection_window = frame.INITIAL_WINDOW_SIZE
        self.max_concurrent_streams = frame.MAX_CONCURRENT_STREAMS
        self.max_frame_size = frame.MAX_FRAME_SIZE
        self.max_header_list_size = frame.MAX_HEADER_LIST_SIZE

        self.streams_in_receiving = {}
        self.streams = deque([])
        self.last_stream_id = 0

    async def execute_once(self, writer: StreamWriter):
        if not self.streams:
            return
        completed_stream = self.streams.popleft()
        http_request = HttpRequest(completed_stream)
        self.last_stream_id = completed_stream.stream_id




        await self.dummy_response(http_request, writer)

    def delete_frame(self, stream_id):
        del self.streams_in_receiving[stream_id]

    async def break_out_frame(self, stream_id, reason: StreamErrorCode, writer: StreamWriter):
        self.delete_frame(stream_id)
        frame = GoAwayFrame(stream_id=0, last_stream_id=self.last_stream_id, error_code=reason.code)
        writer.write(frame.serialize())
        await writer.drain()


    async def dummy_response(self, http_request: HttpRequest, writer: StreamWriter):

        response_headers = [
            (':status', '200'),
            ('content-type', 'text/html'),
        ]

        encoder = Encoder()
        encoded_headers = encoder.encode(response_headers)
        response_headers_frame = HeadersFrame(stream_id=http_request.stream.stream_id)  # 요청과 동일한 stream_id 사용
        response_headers_frame.data = encoded_headers
        response_headers_frame.flags.add('END_HEADERS')
        # response_headers_frame.flags.add('END_STREAM')

        # 2. 응답 DATA 프레임 생성 (응답 본문 데이터)
        response_body = b"<html><body>Hello, HTTP/2!</body></html>"
        response_data_frame = DataFrame(stream_id=http_request.stream.stream_id)  # 요청과 동일한 stream_id 사용
        response_data_frame.data = response_body
        response_data_frame.flags.add('END_STREAM')

        # 3. 서버가 응답 프레임을 클라이언트로 전송
        writer.write(response_headers_frame.serialize())
        writer.write(response_data_frame.serialize())
        await writer.drain()

    def find_stream(self, stream_id) -> Http2Stream:
        if stream_id not in self.streams_in_receiving.keys():
            new_stream = Http2Stream(stream_id, int(self.client_connection_window/self.max_concurrent_streams))
            self.streams_in_receiving[stream_id] = new_stream

        return self.streams_in_receiving.get(stream_id)

    def completed_partial_stream(self, stream_id: int, stream: Http2Stream):
        if stream_id in self.streams_in_receiving.keys():
            del self.streams_in_receiving[stream_id]
        stream.complete_stream()
        self.streams.append(stream)
        print('completed_partial_stream')


async def parse_http2_frame(client_reader: StreamReader, client_writer: StreamWriter):

    await send_settings_frame(client_writer)
    http2_connection = None

    decoder = Decoder()
    while True:
        try:

            if http2_connection:
                await http2_connection.execute_once(client_writer)

            # Header Frame = 9 Byte
            frame_header = await client_reader.read(9)
            # frame_header = await asyncio.wait_for(coro, timeout=3)
            if len(frame_header) < 9:
                print(f"Insufficient data for frame header. {client_reader}")
                break

            frame, length = Frame.parse_frame_header(frame_header)

            frame_payload = await client_reader.read(length)
            frame.parse_body(memoryview(frame_payload))

            if isinstance(frame, SettingsFrame):
                # Client send Ack message as response of Server's Settings Frame.
                if 'ACK' not in frame.flags:
                    http2_connection = Http2Connection(frame)

                    ack_frame = SettingsFrame(flags=['ACK'])
                    client_writer.write(ack_frame.serialize())
                    await client_writer.drain()

            if isinstance(frame, HeadersFrame):
                print('here', frame)
                stream_id = frame.stream_id
                stream = http2_connection.find_stream(stream_id)

                stream.update_raw_headers(frame.data)

                if 'END_STREAM' in frame.flags:
                    stream.complete_stream()


                if 'END_HEADERS' in frame.flags:
                    headers = {}
                    for key, value in decoder.decode(stream.raw_headers):
                        if key == ':method':
                            headers['method'] = value
                        elif key == ':path':
                            headers['path'] = value
                        elif key == ':scheme':
                            headers['protocol'] = 'HTTP/2.0'
                        elif key == ':authority':
                            headers['host'] = value
                        else:
                            headers[key] = value
                    stream.update_headers(headers)
                    stream.complete_headers()

                if stream.stream_status == Http2Stream.DONE and stream.header_status == Http2Stream.DONE:
                    http2_connection.completed_partial_stream(stream_id, stream)


            if isinstance(frame, ContinuationFrame):
                stream_id = frame.stream_id
                stream = http2_connection.find_stream(stream_id)
                stream.update_raw_headers(frame.data)
                if 'END_HEADERS' in frame.flags:
                    headers = {}
                    for key, value in decoder.decode(stream.raw_headers):
                        if key == ':method':
                            headers['method'] = value
                        elif key == ':path':
                            headers['path'] = value
                        elif key == ':scheme':
                            headers['protocol'] = 'HTTP/2.0'
                        elif key == ':authority':
                            headers['host'] = value
                        else:
                            headers[key] = value
                    stream.update_headers(headers)
                    stream.complete_headers()
                if stream.stream_status == Http2Stream.DONE and stream.header_status == Http2Stream.DONE:
                    http2_connection.completed_partial_stream(stream_id, stream)

            if isinstance(frame, DataFrame):
                stream_id = frame.stream_id
                stream = http2_connection.find_stream(stream_id)

                data = frame.data
                if http2_connection.max_frame_size < len(data):
                    await http2_connection.break_out_frame(stream_id, StreamErrorCode.FRAME_SIZE_ERROR, client_writer)

                stream.body += data
                if 'END_STREAM' in frame.flags:
                    http2_connection.completed_partial_stream(stream_id, stream)
                else:
                    stream.update()
                    http2_connection.completed_partial_stream(stream_id, stream)

            if isinstance(frame, PingFrame):
                ack_frame = PingFrame(flags=['ACK'], stream_id=frame.stream_id, opaque_data=frame.opaque_data)
                client_writer.write(ack_frame.serialize())
                await client_writer.drain()

            if isinstance(frame, PriorityFrame):
                a = 1
                # print(f'Priority Frame : {frame.stream_id}')

            if isinstance(frame, WindowUpdateFrame):
                print('window')
                stream_id = frame.stream_id
                stream = http2_connection.find_stream(stream_id)
                # pass

            print(frame)
        except asyncio.TimeoutError:
            print('No need to read buffer.')
            break
    # client_writer.close()
    # await client_writer.wait_closed()


CNT = 0


async def execute(client_reader: StreamReader, client_writer: StreamWriter):
    global CNT

    print(client_reader)
    await parse_http2_frame(client_reader, client_writer)
    client_writer.close()
    await client_writer.wait_closed()

    # encoder = Encoder()
    # response_headers = [
    #     (':status', '200'),
    #     ('content-type', 'text/html'),
    # ]

    # for stream_dict in consume_dq():
    #     pass
        # stream_id = stream_dict['stream_id']
        # encoded_headers = encoder.encode(response_headers)
        # response_headers_frame = HeadersFrame(stream_id=stream_id)  # 요청과 동일한 stream_id 사용
        # response_headers_frame.data = encoded_headers
        # response_headers_frame.flags.add('END_HEADERS')
        #
        # # 2. 응답 DATA 프레임 생성 (응답 본문 데이터)
        # response_body = b"<html><body>Hello, HTTP/2!</body></html>"
        # response_data_frame = DataFrame(stream_id=stream_id)  # 요청과 동일한 stream_id 사용
        # response_data_frame.data = response_body
        # response_data_frame.flags.add('END_STREAM')
        #
        # # 3. 서버가 응답 프레임을 클라이언트로 전송
        # client_writer.write(response_headers_frame.serialize())
        # client_writer.write(response_data_frame.serialize())
        # await client_writer.drain()






async def handle_request(client_reader: StreamReader, client_writer: StreamWriter):
    # print(r)
    is_valid_http2 = await verify_protocol(client_reader)
    if is_valid_http2:
        # print(2)
        await execute(client_reader, client_writer)
    else:
        # https://datatracker.ietf.org/doc/html/rfc9113#name-error-codes
        frame = GoAwayFrame(error_code=1)
        client_writer.write(frame.serialize())
        await client_writer.drain()

    # client_writer.close()









async def main():
    http_server = await asyncio.start_server(handle_request, '127.0.0.1', 8080)

    # async context manager -> 소켓이 닫힐 때까지 기다림.
    async with http_server:
        await asyncio.gather(http_server.serve_forever())


if __name__ == '__main__':
    asyncio.run(main())
