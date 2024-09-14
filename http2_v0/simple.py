import asyncio

import hpack
import hyperframe.frame

from protocol_verifier import verify_protocol

from asyncio.streams import StreamReader, StreamWriter
from hyperframe.frame import Frame, SettingsFrame, PriorityFrame, HeadersFrame, DataFrame, PushPromiseFrame, PingFrame, WindowUpdateFrame, GoAwayFrame, ContinuationFrame, RstStreamFrame, ExtensionFrame
from hpack import Decoder, Encoder, HeaderTuple, HPACKDecodingError
from collections import deque, defaultdict

from error_code import StreamErrorCode

MAX_CONCURRENT_STREAMS = 10


END_STREAM = 'END_STREAM'
END_HEADER = 'END_HEADER'



async def send_settings_frame(client_writer: StreamWriter):
    settings_frame = SettingsFrame(stream_id=0)
    settings_frame.settings = {
        SettingsFrame.MAX_CONCURRENT_STREAMS: MAX_CONCURRENT_STREAMS,
        SettingsFrame.INITIAL_WINDOW_SIZE: 65535
    }

    await send_frame(client_writer, settings_frame)


async def send_frame(client_writer: StreamWriter, frame: Frame):
    client_writer.write(frame.serialize())
    await client_writer.drain()


class HeaderValidateException(Exception):

    def __init__(self, response_frame: Frame, msg: str):
        self.response_frame = response_frame
        self.msg = msg



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
        self.subscriber = asyncio.Queue()

    def update(self):
        self.stream_status = Http2Stream.UPDATING

    # General Headers should be back of pseudo headers.
    def validate_headers(self, decoded_headers: list[tuple[str, str]]):
        PSEUDO_HEADER = 1
        GENERAL_HEADER = 2

        required_headers = set((key for key in [':method', ':path', ':scheme', ':authority']))
        checked_headers = set()

        last_header = None

        for key, value in decoded_headers:

            if key.isupper():
                frame = GoAwayFrame(stream_id=self.stream_id, last_stream_id=0, error_code=StreamErrorCode.PROTOCOL_ERROR.code)
                raise HeaderValidateException(frame, 'Header allows only lower case.')

            if key.startswith(':'):
                if key in checked_headers:
                    frame = GoAwayFrame(stream_id=self.stream_id, last_stream_id=0, error_code=StreamErrorCode.PROTOCOL_ERROR.code)
                    raise HeaderValidateException(frame, f'Duplicated pseudo headers. header: {key}')

                checked_headers.add(key)

            if key.startswith(':') and key not in [':method', ':path', ':scheme', ':authority']:
                frame = GoAwayFrame(stream_id=self.stream_id, error_code=StreamErrorCode.PROTOCOL_ERROR.code)
                raise HeaderValidateException(frame, f'Unknown pseudo headers: {key}')

            if key == ':path' and value == '':
                frame = GoAwayFrame(stream_id=self.stream_id, error_code=StreamErrorCode.PROTOCOL_ERROR.code)
                raise HeaderValidateException(frame, 'The value of :path header cannot be empty.')

            # HTTP/2 should send protocol ERROR when client try to send request with HTTP/1.x headers
            if key.lower() in ['connection', 'keep-alive', 'proxy-connection', 'transfer-encoding', 'upgrade']:
                frame = GoAwayFrame(stream_id=self.stream_id, error_code=StreamErrorCode.PROTOCOL_ERROR.code)
                raise HeaderValidateException(frame, f'HTTP/2 does not support headers which is used in HTTP/1.: {key}')

            # HTTP/2 spec
            if key.lower() == 'te' and value != 'trailers':
                frame = GoAwayFrame(stream_id=self.stream_id, error_code=StreamErrorCode.PROTOCOL_ERROR.code)
                raise HeaderValidateException(frame, f'Invalid header. Only "trailers" is allowed for "te" header value. actual : {value}')


            this_header = PSEUDO_HEADER if key.startswith(':') else GENERAL_HEADER

            if last_header and (last_header > this_header):
                frame = GoAwayFrame(stream_id=self.stream_id, error_code=StreamErrorCode.PROTOCOL_ERROR.code)
                raise HeaderValidateException(frame, 'The pseudo-header field should appear before regular header field.')
            last_header = this_header

        for required_header in required_headers:
            if required_header not in checked_headers:
                frame = GoAwayFrame(stream_id=self.stream_id, error_code=StreamErrorCode.PROTOCOL_ERROR.code)
                raise HeaderValidateException(frame, f'The pseudo header is missed. missed one is {required_header}')

    # :method, :path, :schem, :authority
    def update_pseudo_header(self, decoded_headers: list[tuple[str, str]]) -> dict[str, str]:
        headers = {}
        for key, value in decoded_headers:
            if key == ':method':
                headers['method'] = value
            elif key == ':path':
                headers['path'] = value
            elif key == ':scheme':
                headers['protocol'] = 'HTTP/2.0'
            elif key == ':authority':
                headers['host'] = value
        return headers

    def update_general_headers(self, decoded_headers: list[tuple[str, str]]) -> dict[str, str]:
        headers = {}
        for key, value in decoded_headers:
            if key.startswith(':'):
                continue
            headers[key] = value
        return headers

    def update_headers_new(self, decoded_headers: list[tuple[str, str]]):

        self.validate_headers(decoded_headers)

        pseudo_headers = self.update_pseudo_header(decoded_headers)
        general_headers = self.update_general_headers(decoded_headers)

        self.update_headers(pseudo_headers)
        self.update_headers(general_headers)

    def composite_headers(self):
        pass

    # TODO: NEED TO BE REMOVED.
    def update_headers(self, headers: dict):
        self.headers.update(headers)

    def update_raw_headers(self, raw_header: bytes):
        self.header_status = Http2Stream.UPDATING
        self.raw_headers += raw_header

    def complete_headers(self):
        self.header_status = Http2Stream.DONE

    def complete_stream(self):
        if 'content-length' in self.headers and self.headers.get('content-length') != len(self.body):
            frame = GoAwayFrame(stream_id=self.stream_id, error_code=StreamErrorCode.PROTOCOL_ERROR.code)
            raise HeaderValidateException(frame, f'.')

        self.stream_status = Http2Stream.DONE

    def update_window(self, window_size):
        if not (0 <= window_size <= 2**31-1):
            raise SettingsValueException(GoAwayFrame(error_code=StreamErrorCode.FLOW_CONTROL_ERROR.code))

        if self.client_remain_window + window_size > 2**31-1:
            raise SettingsValueException(RstStreamFrame(stream_id=1, error_code=StreamErrorCode.FLOW_CONTROL_ERROR.code))

        self.client_remain_window = window_size


class HttpRequest:

    def __init__(self, stream: Http2Stream):
        self.headers = stream.headers
        self.body = stream.body
        self.method = stream.headers.get('method')
        self.host = stream.headers.get('host')
        self.protocol = stream.headers.get('protocol')
        self.path = stream.headers.get('path')
        self.stream = stream

class SettingsValueException(Exception):

    def __init__(self, response_frame: Frame):
        self.response_frame = response_frame

async def aiter(q: asyncio.Queue):
    while True:
        yield await q.get()

class Http2Connection:

    INF = 9876543210
    QUE_SIZE = 100

    def __init__(self, frame: SettingsFrame, writer: StreamWriter):
        # https://datatracker.ietf.org/doc/html/rfc9113#name-defined-settings
        settings = frame.settings

        self.is_valid_settings(settings, frame)

        self.enable_connect_protocol = settings.get(frame.ENABLE_CONNECT_PROTOCOL, 0)
        self.enable_push = settings.get(frame.ENABLE_PUSH, 0)
        self.header_table_size = settings.get(frame.HEADER_TABLE_SIZE, 4096)

        self.client_connection_window = settings.get(frame.INITIAL_WINDOW_SIZE, 65535)
        self.max_concurrent_streams = settings.get(frame.MAX_CONCURRENT_STREAMS, MAX_CONCURRENT_STREAMS)

        self.max_frame_size = settings.get(frame.MAX_FRAME_SIZE, 2**14)
        self.max_header_list_size = settings.get(frame.MAX_HEADER_LIST_SIZE, Http2Connection.INF)

        self.streams_in_receiving = {}
        self.streams: asyncio.Queue = asyncio.Queue()
        self.streams_in_que = {}
        self.streams_canceled = set()

        self.last_stream_id = 0
        self.writer = writer

        self.completed_stream_ids = set()
        self.completed_stream_ids_deque = deque([])

        self.window_update_subscriber = {}

        # task = self.consume_complete_stream()
        asyncio.create_task(self.consume_complete_stream())

    async def publish_window_update(self):
        for v in self.window_update_subscriber.values():
            q: asyncio.Queue = v
            await q.put(1)

    def update_window_size(self, frame):

        if isinstance(frame, WindowUpdateFrame):
            window_size = frame.window_increment
            if not (0 <= window_size <= 2**31-1):
                raise SettingsValueException(GoAwayFrame(error_code=StreamErrorCode.FLOW_CONTROL_ERROR.code))

            if not (0 <= window_size + self.client_connection_window <= 2**31-1):
                raise SettingsValueException(GoAwayFrame(error_code=StreamErrorCode.FLOW_CONTROL_ERROR.code))

        if isinstance(frame, SettingsFrame) and frame.INITIAL_WINDOW_SIZE in frame.settings.keys():
            window_size = frame.settings.get(frame.INITIAL_WINDOW_SIZE)
            if not (0 <= window_size <= 2**31-1):
                raise SettingsValueException(GoAwayFrame(error_code=StreamErrorCode.FLOW_CONTROL_ERROR.code))
            if not (0 <= window_size + self.client_connection_window <= 2**31-1):
                raise SettingsValueException(GoAwayFrame(error_code=StreamErrorCode.FLOW_CONTROL_ERROR.code))

            if isinstance(frame, SettingsFrame):
                for stream in self.streams_in_que.values():
                    stream.update_window(window_size)

            self.client_connection_window = window_size

    def update_settings(self, frame):
        settings = frame.settings
        self.is_valid_settings(settings, frame)

        if v := settings.get(frame.ENABLE_CONNECT_PROTOCOL):
            self.enable_connect_protocol = v

        if v := settings.get(frame.ENABLE_PUSH):
            self.enable_push = v

        if v := settings.get(frame.HEADER_TABLE_SIZE):
            self.header_table_size = v

        if v := settings.get(frame.INITIAL_WINDOW_SIZE):
            self.client_connection_window = v

        if v := settings.get(frame.MAX_CONCURRENT_STREAMS):
            self.max_concurrent_streams = v

        if v := settings.get(frame.MAX_FRAME_SIZE):
            self.max_frame_size = v

        if v := settings.get(frame.MAX_HEADER_LIST_SIZE):
            self.max_header_list_size = v

    def cancel_stream(self, stream_id: int):
        if stream_id in self.streams_in_que.keys():
            self.streams_canceled.add(stream_id)

    async def consume_complete_stream(self):
        async for completed_stream in aiter(self.streams):
            if completed_stream.stream_id in self.streams_canceled:
                del self.streams_in_que[completed_stream.stream_id]
                self.streams_canceled.remove(completed_stream.stream_id)
                continue

            http_request = HttpRequest(completed_stream)

            self.last_stream_id = completed_stream.stream_id

            if len(self.completed_stream_ids) >= Http2Connection.QUE_SIZE:
                stream_id = self.completed_stream_ids_deque.popleft()
                self.completed_stream_ids.remove(stream_id)

            self.completed_stream_ids_deque.append(completed_stream.stream_id)
            self.completed_stream_ids.add(completed_stream.stream_id)

            await self.dummy_response(http_request, self.writer)
            del self.streams_in_que[completed_stream.stream_id]


    def is_valid_settings(self, settings, frame):
        if v := settings.get(frame.ENABLE_CONNECT_PROTOCOL):
            if int(v) not in (0, 1):
                raise SettingsValueException(GoAwayFrame(error_code=StreamErrorCode.PROTOCOL_ERROR.code))

        if v := settings.get(frame.ENABLE_PUSH):
            if int(v) not in (0, 1):
                raise SettingsValueException(GoAwayFrame(error_code=StreamErrorCode.PROTOCOL_ERROR.code))

        if v := settings.get(frame.HEADER_TABLE_SIZE):
            if v < 0:
                return False

        if v := settings.get(frame.INITIAL_WINDOW_SIZE):
            if not (0 < v <= 2**31-1):
                raise SettingsValueException(GoAwayFrame(error_code=StreamErrorCode.FLOW_CONTROL_ERROR.code))

        if v := settings.get(frame.MAX_CONCURRENT_STREAMS):
            if v < 0:
                return False

        if v := settings.get(frame.MAX_FRAME_SIZE):
            # The initial value is 214 (16,384) octets. The value advertised by an endpoint MUST be between this initial value and the maximum allowed frame size (224-1 or 16,777,215 octets), inclusive.
            if not (16384 <= v <= 2**24 - 1):
                raise SettingsValueException(GoAwayFrame(error_code=StreamErrorCode.PROTOCOL_ERROR.code))

        if v := settings.get(frame.MAX_HEADER_LIST_SIZE):
            if v < 0:
                return False


        #Frame size should have range self.max_fame_size < x < 2**24 - 1
        return True

    def remove_stream_by_force(self, stream_id):
        if stream_id in self.streams_in_receiving.keys():
            del self.streams_in_receiving[stream_id]


    def delete_frame(self, stream_id):
        if stream_id in self.streams_in_receiving.keys():
            del self.streams_in_receiving[stream_id]

    def has_been_done(self, stream_id):
        return stream_id in self.completed_stream_ids or stream_id in self.streams_in_que.keys()

    async def break_out_frame(self, stream_id, reason: StreamErrorCode, writer: StreamWriter):
        self.delete_frame(stream_id)
        frame = GoAwayFrame(stream_id=0, last_stream_id=self.last_stream_id, error_code=reason.code)
        writer.write(frame.serialize())
        await writer.drain()


    async def dummy_response(self, http_request: HttpRequest, writer: StreamWriter):

        response_headers = [
            (':status', '200'),
            ('content-type', 'text/plain-text'),
        ]

        encoder = Encoder()
        encoded_headers = encoder.encode(response_headers)

        # Header Frame does not care about window remain.
        response_headers_frame = HeadersFrame(stream_id=http_request.stream.stream_id)  # 요청과 동일한 stream_id 사용
        response_headers_frame.data = encoded_headers
        response_headers_frame.flags.add('END_HEADERS')
        writer.write(response_headers_frame.serialize())
        await writer.drain()
        # response_headers_frame.flags.add('END_STREAM')

        # 2. 응답 DATA 프레임 생성 (응답 본문 데이터)
        response_body = b"1"
        response_data_frame = DataFrame(stream_id=http_request.stream.stream_id)  # 요청과 동일한 stream_id 사용
        response_data_frame.data = response_body
        response_data_frame.flags.add('END_STREAM')
        data_size = len(response_data_frame.data)

        if http_request.stream.client_remain_window < data_size:
            print(f'SHOULD WAIT. {self.client_connection_window}, {http_request.stream.client_remain_window}')
            async for _ in aiter(http_request.stream.subscriber):
                if http_request.stream.client_remain_window >= data_size:
                    break
        self.client_connection_window -= data_size
        writer.write(response_data_frame.serialize())
        await writer.drain()
        del self.window_update_subscriber[http_request.stream.stream_id]


    def subscribe(self, stream_id, que):
        self.window_update_subscriber[stream_id] = que



    def find_stream(self, stream_id, frame: Frame) -> Http2Stream:
        if not (isinstance(frame, RstStreamFrame) or
                isinstance(frame, SettingsFrame) or
                isinstance(frame, WindowUpdateFrame) or
                isinstance(frame, ExtensionFrame)) and stream_id not in self.streams_in_receiving.keys():
            new_stream = Http2Stream(stream_id, int(self.client_connection_window))
            self.streams_in_receiving[stream_id] = new_stream
            self.subscribe(stream_id, new_stream.subscriber)

        if self.streams_in_receiving.get(stream_id):
            return self.streams_in_receiving.get(stream_id)

        if self.streams_in_que.get(stream_id):
            return self.streams_in_que.get(stream_id)

        return self.streams_in_receiving.get(stream_id)

    async def completed_partial_stream(self, stream_id: int, stream: Http2Stream):
        if stream_id in self.streams_in_receiving.keys():
            del self.streams_in_receiving[stream_id]
        stream.complete_stream()
        self.streams_in_que[stream_id] = stream
        await self.streams.put(stream)

    def update_stream(self, stream_id: int, stream: Http2Stream):
        self.streams_in_receiving[stream_id] = stream



async def parse_http2_frame(client_reader: StreamReader, client_writer: StreamWriter):

    await send_settings_frame(client_writer)
    http2_connection = None

    decoder = Decoder()
    last_frame = None
    while True:
        try:

            # Header Frame = 9 Byte
            frame_header = await client_reader.read(9)
            if len(frame_header) < 9:
                # await asyncio.sleep(0.5)
                await http2_connection.break_out_frame(0, StreamErrorCode.COMPRESSION_ERROR, client_writer)
                print(f"Insufficient data for frame header. {client_reader}")
                break

            try:
                frame, length = Frame.parse_frame_header(frame_header)
                print(frame, length)
            except hyperframe.frame.InvalidDataError as e:
                await http2_connection.break_out_frame(0, StreamErrorCode.PROTOCOL_ERROR, client_writer)
                continue

            frame_payload = await client_reader.read(length)
            frame.parse_body(memoryview(frame_payload))

            if frame.stream_id > 0 and (frame.stream_id % 2) == 0:
                await http2_connection.break_out_frame(0, StreamErrorCode.PROTOCOL_ERROR, client_writer)
                continue

            if http2_connection:
                print(f'size. {len(http2_connection.streams_in_receiving.keys()) + len(http2_connection.streams_in_que.keys())}')

            if http2_connection and frame.stream_id > 0 and http2_connection.max_concurrent_streams < len(http2_connection.streams_in_receiving.keys()) + len(http2_connection.streams_in_que.keys()) + 1:
                print('MAX REFUSED CONCURRENT STREAM VIOLATION')
                await http2_connection.break_out_frame(0, StreamErrorCode.REFUSED_STREAM, client_writer)
                continue

            if last_frame and frame.stream_id > 0 and last_frame.stream_id > frame.stream_id:
                await http2_connection.break_out_frame(0, StreamErrorCode.PROTOCOL_ERROR, client_writer)
                continue

            if isinstance(frame, SettingsFrame):
                # Client send Ack message as response of Server's Settings Frame.
                print(frame)
                if 'ACK' not in frame.flags:
                    if not http2_connection:
                        http2_connection = Http2Connection(frame, client_writer)

                    http2_connection.update_window_size(frame)
                    http2_connection.update_settings(frame)

                    ack_frame = SettingsFrame(flags=['ACK'])
                    client_writer.write(ack_frame.serialize())
                    await client_writer.drain()
                continue

            if isinstance(frame, HeadersFrame):
                stream_id = frame.stream_id

                if stream_id == frame.depends_on:
                    http2_connection.cancel_stream(stream_id)
                    await http2_connection.break_out_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR, client_writer)
                    continue

                if http2_connection.has_been_done(stream_id):
                    http2_connection.cancel_stream(stream_id)
                    await http2_connection.break_out_frame(stream_id, StreamErrorCode.STREAM_CLOSED, client_writer)
                    continue

                stream = http2_connection.find_stream(stream_id, frame)

                data = frame.data

                # Not Trailer header case. -> invalid status.
                if stream.header_status == Http2Stream.DONE and stream.stream_status == Http2Stream.DONE:
                    http2_connection.cancel_stream(stream_id)
                    await http2_connection.break_out_frame(stream_id, StreamErrorCode.STREAM_CLOSED, client_writer)
                    continue

                # Invalid case
                if stream.header_status == Http2Stream.DONE and END_STREAM not in frame.flags:
                    http2_connection.cancel_stream(stream_id)
                    await http2_connection.break_out_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR, client_writer)
                    continue


                if http2_connection.max_frame_size < len(data):
                    http2_connection.cancel_stream(stream_id)
                    await http2_connection.break_out_frame(stream_id, StreamErrorCode.FRAME_SIZE_ERROR, client_writer)
                    continue

                stream.update_raw_headers(data)

                if 'END_STREAM' in frame.flags:
                    stream.complete_stream()

                if 'END_HEADERS' in frame.flags:
                    try:
                        decoded_headers = decoder.decode(stream.raw_headers)
                        print(f'{decoded_headers=}')
                    except HPACKDecodingError as e:
                        await http2_connection.break_out_frame(0, StreamErrorCode.COMPRESSION_ERROR, client_writer)
                    else:
                        stream.update_headers_new(decoded_headers)
                        stream.complete_headers()

                http2_connection.update_stream(stream_id, stream)
                if stream.stream_status == Http2Stream.DONE and stream.header_status == Http2Stream.DONE:
                    await http2_connection.completed_partial_stream(stream_id, stream)

            # HTTP/2 프로토콜에 따르면, 헤더 블록이 여러 프레임에 걸쳐 전송될 때, HEADERS 프레임과 CONTINUATION 프레임은 연속적으로 전송되어야 합니다. 즉, 헤더 블록이 완전히 전송되기 전까지는 다른 스트림에 대한 프레임을 포함하여 다른 유형의 프레임이 전송되어서는 안 됩니다.
            if isinstance(frame, ContinuationFrame):
                stream_id = frame.stream_id

                if (stream_id not in http2_connection.streams_in_receiving.keys()):
                    http2_connection.cancel_stream(stream_id)
                    await http2_connection.break_out_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR, client_writer)

                if frame.stream_id > 0 and last_frame.stream_id > frame.stream_id:
                    http2_connection.cancel_stream(stream_id)
                    await http2_connection.break_out_frame(0, StreamErrorCode.PROTOCOL_ERROR, client_writer)
                    continue

                if http2_connection.has_been_done(stream_id):
                    http2_connection.cancel_stream(stream_id)
                    await http2_connection.break_out_frame(stream_id, StreamErrorCode.STREAM_CLOSED, client_writer)
                    continue

                data = frame.data
                stream = http2_connection.find_stream(stream_id, frame)

                if stream.header_status == Http2Stream.DONE:
                    http2_connection.cancel_stream(stream_id)
                    await http2_connection.break_out_frame(stream_id, StreamErrorCode.STREAM_CLOSED, client_writer)
                    continue

                if not((isinstance(last_frame, HeadersFrame) or isinstance(last_frame, ContinuationFrame)) and last_frame.stream_id == stream_id):
                    http2_connection.cancel_stream(stream_id)
                    await http2_connection.break_out_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR, client_writer)
                    continue

                if http2_connection.max_frame_size < len(data):
                    http2_connection.cancel_stream(stream_id)
                    await http2_connection.break_out_frame(stream_id, StreamErrorCode.FRAME_SIZE_ERROR, client_writer)
                    continue

                stream.update_raw_headers(frame.data)
                if 'END_HEADERS' in frame.flags:
                    headers = {}
                    try:
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
                    except HPACKDecodingError as e:
                        await http2_connection.break_out_frame(0, StreamErrorCode.COMPRESSION_ERROR, client_writer)

                http2_connection.update_stream(stream_id, stream)
                if stream.stream_status == Http2Stream.DONE and stream.header_status == Http2Stream.DONE:
                    await http2_connection.completed_partial_stream(stream_id, stream)

            if isinstance(frame, DataFrame):
                stream_id = frame.stream_id

                if http2_connection.has_been_done(stream_id):
                    http2_connection.cancel_stream(stream_id)
                    await http2_connection.break_out_frame(stream_id, StreamErrorCode.STREAM_CLOSED, client_writer)
                    continue

                stream = http2_connection.find_stream(stream_id, frame)
                data = frame.data

                if stream.header_status != Http2Stream.DONE:
                    http2_connection.cancel_stream(stream_id)
                    await http2_connection.break_out_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR, client_writer)
                    continue

                if stream.stream_status == Http2Stream.DONE:
                    http2_connection.cancel_stream(stream_id)
                    await http2_connection.break_out_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR, client_writer)
                    continue

                if http2_connection.max_frame_size < len(data):
                    http2_connection.cancel_stream(stream_id)
                    await http2_connection.break_out_frame(stream_id, StreamErrorCode.FRAME_SIZE_ERROR, client_writer)
                    continue

                stream.body += data
                if 'END_STREAM' in frame.flags:
                    await http2_connection.completed_partial_stream(stream_id, stream)
                else:
                    stream.update()
                    # await http2_connection.completed_partial_stream(stream_id, stream)
                http2_connection.update_stream(stream_id, stream)

            if isinstance(frame, PingFrame):
                if 'ACK' in frame.flags:
                    continue
                ack_frame = PingFrame(flags=['ACK'], stream_id=frame.stream_id, opaque_data=frame.opaque_data)
                client_writer.write(ack_frame.serialize())
                await client_writer.drain()

            if isinstance(frame, PriorityFrame):
                stream_id = frame.stream_id

                if stream_id == frame.depends_on:
                    http2_connection.cancel_stream(stream_id)
                    await http2_connection.break_out_frame(0, StreamErrorCode.PROTOCOL_ERROR, client_writer)
                    continue

                if (
                        stream_id in http2_connection.streams_in_receiving.keys()
                ):
                    http2_connection.cancel_stream(stream_id)
                    await http2_connection.break_out_frame(0, StreamErrorCode.PROTOCOL_ERROR, client_writer)
                    continue

                a = 1
                # print(f'Priority Frame : {frame.stream_id}')

            if isinstance(frame, WindowUpdateFrame):
                print(frame)
                stream_id = frame.stream_id
                # stream = http2_connection.find_stream(stream_id, frame)
                if (
                        stream_id > 0 and
                        stream_id not in http2_connection.streams_in_receiving.keys() and
                        stream_id not in http2_connection.streams_in_que.keys() and
                        stream_id not in http2_connection.completed_stream_ids
                ):
                    http2_connection.cancel_stream(stream_id)
                    await http2_connection.break_out_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR, client_writer)
                    continue

                if stream_id == 0:
                    http2_connection.update_window_size(frame)
                else:
                    stream = http2_connection.find_stream(stream_id, frame)
                    stream.update_window(frame.window_increment)

                await http2_connection.publish_window_update()
                continue


            if isinstance(frame, RstStreamFrame):
                stream_id = frame.stream_id
                stream = http2_connection.find_stream(stream_id, frame)

                if not stream:
                    http2_connection.cancel_stream(stream_id)
                    await http2_connection.break_out_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR, client_writer)
                    continue

                http2_connection.remove_stream_by_force(stream_id)
                await http2_connection.break_out_frame(stream_id, StreamErrorCode.STREAM_CLOSED, client_writer)

            if isinstance(frame, ExtensionFrame):
                stream_id = frame.stream_id
                stream = http2_connection.find_stream(stream_id, frame)

                if stream and (stream.stream_status != Http2Stream.INIT or stream.header_status != Http2Stream.INIT):
                    http2_connection.cancel_stream(stream_id)
                    await http2_connection.break_out_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR, client_writer)
                    continue

                if last_frame:
                    last_stream = http2_connection.find_stream(last_frame.stream_id, last_frame)
                    if last_stream and (last_stream.stream_status != Http2Stream.INIT or last_stream.header_status != Http2Stream.INIT):
                        http2_connection.cancel_stream(stream_id)
                        await http2_connection.break_out_frame(stream_id, StreamErrorCode.PROTOCOL_ERROR, client_writer)
                        continue

            if isinstance(frame, HeadersFrame) or isinstance(frame, DataFrame):
                last_frame = frame
            print(frame)
        except asyncio.TimeoutError:
            print('No need to read buffer.')
            break
        except hyperframe.frame.InvalidDataError as e:
            print(e)
            if isinstance(frame, SettingsFrame):
                await http2_connection.break_out_frame(0, StreamErrorCode.FRAME_SIZE_ERROR, client_writer)
            else:
                await http2_connection.break_out_frame(0, StreamErrorCode.PROTOCOL_ERROR, client_writer)
            continue
        except hyperframe.frame.InvalidPaddingError as e:
            print(e)
            await http2_connection.break_out_frame(0, StreamErrorCode.PROTOCOL_ERROR, client_writer)
            continue
        except hyperframe.frame.InvalidFrameError as e:
            print(e)
            await http2_connection.break_out_frame(0, StreamErrorCode.FRAME_SIZE_ERROR, client_writer)
            continue
        except SettingsValueException as e:
            print(e)
            stream_id = e.response_frame.stream_id
            if http2_connection and stream_id and stream_id > 0:
                http2_connection.cancel_stream(stream_id)
            client_writer.write(e.response_frame.serialize())
            await client_writer.drain()
            continue
        # except Exception as e:
        #     print(e)
        #     continue
        # except Exception as e:
        #     print(e)

        # except Exception as e:
        #     print(e)
    # client_writer.close()
    # await client_writer.wait_closed()


# 헤더 -> Continuation -> DATA 형태로 와야함.
# 헤더 -> DATA -> 헤더 형식으로 오려면 trailering 형태여야 함.

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
