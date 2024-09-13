import asyncio

from hyperframe.frame import Frame, SettingsFrame, PriorityFrame, HeadersFrame, DataFrame, PushPromiseFrame, PingFrame, WindowUpdateFrame, GoAwayFrame, ContinuationFrame, RstStreamFrame, ExtensionFrame
from collections import deque

from http2_exception import HeaderValidateException
from error_code import StreamErrorCode

from http2_exception import SettingsValueException
from utils import GeneratorWrapper


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

    # :method, :path, :scheme, :authority
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


class Http2StreamQueue:

    COMPLETED_QUE_SIZE = 100

    def __init__(self):
        self.streams_in_receiving = {}
        self.streams: asyncio.Queue = asyncio.Queue()
        self.streams_in_que = {}
        self.streams_canceled = set()
        self.completed_stream_ids = set()
        self.completed_stream_ids_deque = deque([])

    async def publish_end(self):
        await self.streams.put(GeneratorWrapper.TERM_SIGNAL)

    def find_stream_in_receiving(self, stream_id: int) -> Http2Stream:
        return self.streams_in_receiving.get(stream_id)

    def find_stream_in_processing(self, stream_id: int) -> Http2Stream:
        return self.streams_in_que.get(stream_id)

    def get_streams_in_receiving(self, stream_id: int) :
        return self.streams_in_receiving

    def get_streams(self):
        return self.streams

    def get_streams_in_que(self):
        return self.streams_in_que

    def get_streams_canceled(self):
        return self.streams_canceled

    def not_existed_anywhere(self, stream_id):
        return (
                not self.is_in_receiving(stream_id) and
                not self.is_in_processing(stream_id) and
                not self.is_in_completed(stream_id)
                )

    def is_in_receiving(self, stream_id: int) -> bool:
        return stream_id in self.streams_in_receiving.keys()

    def is_in_processing(self, stream_id: int) -> bool:
        return stream_id in self.streams_in_que.keys()

    def is_in_completed(self, stream_id: int) -> bool:
        return stream_id in self.completed_stream_ids

    def qsize_in_receiving(self) -> int:
        return len(self.streams_in_receiving)

    def qsize_in_processing(self) -> int:
        return len(self.streams_in_que)

    def total_qsize(self) -> int:
        return self.qsize_in_receiving() + self.qsize_in_processing()

    def cancel_stream(self, stream_id: int):
        self.streams_canceled.add(stream_id)

    def add_new_stream_in_receiving(self, stream_id: int, new_stream: Http2Stream):
        self.streams_in_receiving[stream_id] = new_stream

    def is_canceled_stream(self, stream_id: int):
        if stream_id in self.streams_canceled:
            del self.streams_in_que[stream_id]
            self.streams_canceled.remove(stream_id)
            return True
        return False

    def remove_stream_from_receiving(self, stream_id: int):
        if self.is_in_receiving(stream_id):
            del self.streams_in_receiving[stream_id]

    def maybe_completed_que_overflows(self):
        if len(self.completed_stream_ids) >= Http2StreamQueue.COMPLETED_QUE_SIZE:
            stream_id = self.completed_stream_ids_deque.popleft()
            self.completed_stream_ids.remove(stream_id)

    async def add_new_stream_in_processing(self, stream_id: int, stream: Http2Stream):
        self.streams_in_que[stream_id] = stream
        await self.streams.put(stream)

    def add_completed_stream(self, stream_id: int):
        self.completed_stream_ids_deque.append(stream_id)
        self.completed_stream_ids.add(stream_id)
        try:
            del self.streams_in_que[stream_id]
        except Exception:
            pass

    def update_stream_in_receiving(self, stream_id: int, stream: Http2Stream):
        self.streams_in_receiving[stream_id] = stream

    def has_been_done(self, stream_id: int) -> bool:
        return stream_id in self.completed_stream_ids or stream_id in self.streams_in_que.keys()


    async def put_stream(self, stream: Http2Stream):
        await self.streams.put(stream)


class Http2Settings:

    # We need to define the known settings, they may as well be class
    # attributes.
    #: The byte that signals the SETTINGS_HEADER_TABLE_SIZE setting.
    HEADER_TABLE_SIZE = 0x01
    #: The byte that signals the SETTINGS_ENABLE_PUSH setting.
    ENABLE_PUSH = 0x02
    #: The byte that signals the SETTINGS_MAX_CONCURRENT_STREAMS setting.
    MAX_CONCURRENT_STREAMS = 0x03
    #: The byte that signals the SETTINGS_INITIAL_WINDOW_SIZE setting.
    INITIAL_WINDOW_SIZE = 0x04
    #: The byte that signals the SETTINGS_MAX_FRAME_SIZE setting.
    MAX_FRAME_SIZE = 0x05
    #: The byte that signals the SETTINGS_MAX_HEADER_LIST_SIZE setting.
    MAX_HEADER_LIST_SIZE = 0x06
    #: The byte that signals SETTINGS_ENABLE_CONNECT_PROTOCOL setting.
    ENABLE_CONNECT_PROTOCOL = 0x08

    INF = 9876543210
    MAX_CONCURRENT_STREAMS_COUNT = 10

    def __init__(self):
        # https://datatracker.ietf.org/doc/html/rfc9113#name-defined-settings
        # https://datatracker.ietf.org/doc/html/rfc7540#section-11.3
        # Frame init setting.

        self._enable_connect_protocol: int = 0
        self._enable_push: int = 0
        self._header_table_size: int = 4096

        self._client_connection_window: int = 65535
        self._max_concurrent_streams: int = Http2Settings.MAX_CONCURRENT_STREAMS_COUNT

        self._max_frame_size: int = 2**14
        self._max_header_list_size: int = Http2Settings.INF

    def update_settings(self, frame: SettingsFrame):

        settings = frame.settings

        self.check_settings_if_throw(settings)

        self._enable_connect_protocol = settings.get(Http2Settings.ENABLE_CONNECT_PROTOCOL,
                                                     self._enable_connect_protocol)
        self._enable_push = settings.get(Http2Settings.ENABLE_PUSH,
                                         self._enable_push)
        self._header_table_size = settings.get(Http2Settings.HEADER_TABLE_SIZE,
                                               self._header_table_size)

        self._client_connection_window = settings.get(Http2Settings.INITIAL_WINDOW_SIZE,
                                                      self._client_connection_window)
        self._max_concurrent_streams = settings.get(Http2Settings.MAX_CONCURRENT_STREAMS,
                                                    self._max_concurrent_streams)

        self._max_frame_size = settings.get(Http2Settings.MAX_FRAME_SIZE,
                                            self._max_frame_size)
        self._max_header_list_size = settings.get(Http2Settings.MAX_HEADER_LIST_SIZE,
                                                  self._max_header_list_size)

    def get_client_connection_window(self) -> int:
        return self._client_connection_window

    def add_connection_window(self, increment: int):
        self._client_connection_window += increment

    def reduce_connection_window(self, reduce_amount: int):
        self._client_connection_window -= reduce_amount

    def set_connection_window_size(self, window_size: int):
        self._client_connection_window = window_size

    def max_concurrent_streams(self):
        return self._max_concurrent_streams

    def max_frame_size(self):
        return self._max_frame_size

    def check_settings_if_throw(self, settings: dict[int, int]) -> None:

        if v := settings.get(Http2Settings.ENABLE_CONNECT_PROTOCOL):
            if int(v) not in (0, 1):
                raise SettingsValueException(GoAwayFrame(error_code=StreamErrorCode.PROTOCOL_ERROR.code))

        if v := settings.get(Http2Settings.ENABLE_PUSH):
            if int(v) not in (0, 1):
                raise SettingsValueException(GoAwayFrame(error_code=StreamErrorCode.PROTOCOL_ERROR.code))

        if v := settings.get(Http2Settings.HEADER_TABLE_SIZE):
            if v < 0:
                raise SettingsValueException(GoAwayFrame(error_code=StreamErrorCode.PROTOCOL_ERROR.code))

        if v := settings.get(Http2Settings.INITIAL_WINDOW_SIZE):
            if not (0 < v <= 2**31-1):
                raise SettingsValueException(GoAwayFrame(error_code=StreamErrorCode.FLOW_CONTROL_ERROR.code))

        if v := settings.get(Http2Settings.MAX_CONCURRENT_STREAMS):
            if v < 0:
                raise SettingsValueException(GoAwayFrame(error_code=StreamErrorCode.PROTOCOL_ERROR.code))

        if v := settings.get(Http2Settings.MAX_FRAME_SIZE):
            # The initial value is 214 (16,384) octets.
            # The value advertised by an endpoint MUST be between this initial value and the maximum allowed frame size (224-1 or 16,777,215 octets), inclusive.
            if not (16384 <= v <= 2**24 - 1):
                raise SettingsValueException(GoAwayFrame(error_code=StreamErrorCode.PROTOCOL_ERROR.code))

        if v := settings.get(Http2Settings.MAX_HEADER_LIST_SIZE):
            if v < 0:
                raise SettingsValueException(GoAwayFrame(error_code=StreamErrorCode.PROTOCOL_ERROR.code))
