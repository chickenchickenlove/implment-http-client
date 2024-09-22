import uuid
import asyncio

from typing import Union
from hyperframe.frame import Frame, SettingsFrame, PriorityFrame, HeadersFrame, DataFrame, PushPromiseFrame, PingFrame, WindowUpdateFrame, GoAwayFrame, ContinuationFrame, RstStreamFrame, ExtensionFrame
from collections import deque

from http_2.http2_exception import HeaderValidateException, SettingsValueException
from http_2.error_code import StreamErrorCode

# https://datatracker.ietf.org/doc/html/rfc9113#name-stream-states
class Http2StreamState:

    # For not created stream yet.
    IDLE = 'IDLE'

    # Related with PushPromise
    RESERVED = 'RESERVED'

    # A stream in the "open" state may be used by both peers to send frames of any type.
    # In this state, sending peers observe advertised stream-level flow-control limits (Section 5.2).
    # From this state, either endpoint can send a frame with an END_STREAM flag set,
    # which causes the stream to transition into one of the "half-closed" states.
    # An endpoint sending an END_STREAM flag causes the stream state to become "half-closed (local)";
    # an endpoint receiving an END_STREAM flag causes the stream state to become "half-closed (remote)".
    OPEN = 'OPEN'

    # A stream that is "half-closed (remote)" is no longer being used by the peer to send frames.
    # In this state, an endpoint is no longer obligated to maintain a receiver flow-control window.
    #
    # If an endpoint receives additional frames, other than WINDOW_UPDATE, PRIORITY, or RST_STREAM, for a stream that is in this state, it MUST respond with a stream error (Section 5.4.2) of type STREAM_CLOSED.
    #
    # A stream that is "half-closed (remote)" can be used by the endpoint to send frames of any type. In this state, the endpoint continues to observe advertised stream-level flow-control limits (Section 5.2).
    #
    # A stream can transition from this state to "closed" by sending a frame with the END_STREAM flag set or when either peer sends a RST_STREAM frame.
    HALF_CLOSED = 'HALF_CLOSED'

    # Boty server and client send END_STREAM FLAG. so Both can't send any request at all.
    CLOSE = 'CLOSED'


class Http2StreamAction:

    UPDATE_HEADER = 'UPDATE_HEADER'
    UPDATE_DATA = 'UPDATE_DATA'


class Http2Stream:

    INIT = 'INIT'
    UPDATING = 'UPDATING'
    DONE = 'DONE'

    PSEUDO_HEADER = 1
    GENERAL_HEADER = 2

    def __init__(self,
                 stream_id: int,
                 init_window: int):
        self._stream_id = stream_id
        self._client_remain_window = init_window
        self._raw_headers = b''
        self._raw_body = b''

        self._headers = {}
        self._body = ''

        self._header_status = Http2Stream.INIT
        self._stream_status = Http2Stream.INIT
        self._subscriber = TerminateAwareAsyncioQue()
        self._state = Http2StreamState.OPEN

    @property
    def stream_id(self):
        return self._stream_id

    @property
    def client_remain_window(self):
        return self._client_remain_window

    @property
    def raw_headers(self):
        return self._raw_headers

    @property
    def raw_body(self):
        return self._raw_body

    @property
    def headers(self):
        return self._headers

    @property
    def body(self):
        return self._body

    @property
    def header_status(self):
        return self._header_status

    @property
    def stream_status(self):
        return self._stream_status

    @property
    def subscriber(self):
        return self._subscriber

    @property
    def state(self):
        return self._state

    def update(self):
        self._stream_status = Http2Stream.UPDATING

    def close_state(self):
        self._state = Http2StreamState.CLOSE

    def is_allowed_frame(self, frame: Frame):

        # https://datatracker.ietf.org/doc/html/rfc9113#section-5.1-7.8.1
        # A stream in the "open" state may be used by both peers to send frames of any type.
        # In this state, sending peers observe advertised stream-level flow-control limits (Section 5.2).
        if self.state == Http2StreamState.OPEN:
            return True, None

        # STATE IS HALF_CLOSED. (Server got END_STREAM FLAG, however not END_HEADERS FLAG yet)
        if self.state == Http2StreamState.HALF_CLOSED:
            if self.header_status == Http2Stream.DONE:

                # If an endpoint receives additional frames, other than WINDOW_UPDATE, PRIORITY, or RST_STREAM,
                # for a stream that is in this state, it MUST respond with a stream error (Section 5.4.2) of type STREAM_CLOSED.
                if not isinstance(frame, (WindowUpdateFrame, PriorityFrame, RstStreamFrame, SettingsFrame)):
                    return False, StreamErrorCode.STREAM_CLOSED

            if self.header_status != Http2Stream.DONE:
                if not isinstance(frame, (WindowUpdateFrame, PriorityFrame, RstStreamFrame, HeadersFrame, ContinuationFrame, SettingsFrame)):
                    return False, StreamErrorCode.PROTOCOL_ERROR

            # Not Trailer header case. -> invalid status.
            if self.header_status == Http2Stream.DONE and self.stream_status == Http2Stream.DONE and isinstance(frame, HeadersFrame):
                return False, StreamErrorCode.STREAM_CLOSED

        if self.state == Http2StreamState.CLOSE:
            if not isinstance(frame, (PriorityFrame)):
                return False, StreamErrorCode.PROTOCOL_ERROR

        return True, None

    def is_action_allowed(self, action):
        # https://datatracker.ietf.org/doc/html/rfc9113#name-headers
        # HEADERS frames can be sent on a stream in the "idle", "reserved (local)", "open", or "half-closed (remote)" state.
        if action == Http2StreamAction.UPDATE_HEADER:
            if self.state == Http2StreamState.HALF_CLOSED and self.header_status == Http2Stream.DONE:
                raise Exception()

        if action == Http2StreamAction.UPDATE_DATA:
            if self.state != Http2StreamState.OPEN:
                raise Exception()

    def update_raw_body(self, data):
        self.is_action_allowed(Http2StreamAction.UPDATE_DATA)
        self._raw_body += data

    # General Headers should be back of pseudo headers.
    def validate_headers(self, decoded_headers: list[tuple[str, str]]):
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
                raise HeaderValidateException(frame,
                      f'HTTP/2 does not support headers which is used in HTTP/1.: {key}')

            # HTTP/2 spec
            if key.lower() == 'te' and value != 'trailers':
                frame = GoAwayFrame(stream_id=self.stream_id, error_code=StreamErrorCode.PROTOCOL_ERROR.code)
                raise HeaderValidateException(frame,
                      f'Invalid header. Only "trailers" is allowed for "te" header value. actual : {value}')

            this_header = Http2Stream.PSEUDO_HEADER if key.startswith(':') else Http2Stream.GENERAL_HEADER

            if last_header and (last_header > this_header):
                frame = GoAwayFrame(stream_id=self.stream_id, error_code=StreamErrorCode.PROTOCOL_ERROR.code)
                raise HeaderValidateException(frame,
                      'The pseudo-header field should appear before regular header field.')
            last_header = this_header

        for required_header in required_headers:
            if required_header not in checked_headers:
                frame = GoAwayFrame(stream_id=self.stream_id, error_code=StreamErrorCode.PROTOCOL_ERROR.code)
                raise HeaderValidateException(
                    frame, f'The pseudo header is missed. missed one is {required_header}')

    # :method, :path, :scheme, :authority
    def update_pseudo_header(self, decoded_headers: list[tuple[str, str]]) -> dict[str, str]:
        headers = {}
        for key, value in decoded_headers:
            if key == ':method':
                headers['method'] = value
            elif key == ':path':
                headers['path'] = value
            elif key == ':scheme':
                headers['protocol'] = 'HTTP/2'
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

        self.is_action_allowed(Http2StreamAction.UPDATE_HEADER)

        self.validate_headers(decoded_headers)

        pseudo_headers = self.update_pseudo_header(decoded_headers)
        general_headers = self.update_general_headers(decoded_headers)

        self.headers.update(pseudo_headers)
        self.headers.update(general_headers)

    def update_raw_headers(self, raw_header: bytes):
        self.is_action_allowed(Http2StreamAction.UPDATE_HEADER)

        self._header_status = Http2Stream.UPDATING
        self._raw_headers += raw_header

    def complete_headers(self):
        self._header_status = Http2Stream.DONE

    def complete_stream(self):
        if 'content-length' in self.headers and self.headers.get('content-length') != len(self.body):
            frame = GoAwayFrame(stream_id=self.stream_id, error_code=StreamErrorCode.PROTOCOL_ERROR.code)
            raise HeaderValidateException(frame, f'Content-Length and Body Size do not match.')

        self._body = self.raw_body.decode()
        self._stream_status = Http2Stream.DONE
        self._state = Http2StreamState.HALF_CLOSED

    def update_window(self, window_size):
        if not (0 <= window_size <= 2**31-1):
            raise SettingsValueException(GoAwayFrame(error_code=StreamErrorCode.FLOW_CONTROL_ERROR.code))

        if self.client_remain_window + window_size > 2**31-1:
            raise SettingsValueException(RstStreamFrame(stream_id=1, error_code=StreamErrorCode.FLOW_CONTROL_ERROR.code))

        self._client_remain_window = window_size


class Http2StreamQueue:

    COMPLETED_QUE_SIZE = 100

    def __init__(self):
        # Open State
        self.streams_in_open = {}

        # Canceled streams.
        self.streams_canceled = set()

        # Closed State.
        self.closed_stream_ids = set()
        self.closed_stream_ids_deque = deque([])

        # Half-closed and header status is done.
        self.streams: TerminateAwareAsyncioQue = TerminateAwareAsyncioQue()
        self.streams_in_que = {}

    async def publish_end(self):
        await self.streams.send_term_signal()

    def find_stream_in_open(self, stream_id: int) -> Http2Stream:
        return self.streams_in_open.get(stream_id)

    def find_stream_in_processing(self, stream_id: int) -> Http2Stream:
        return self.streams_in_que.get(stream_id)

    def get_streams(self):
        return self.streams

    def get_streams_in_que(self):
        return self.streams_in_que

    def get_streams_canceled(self):
        return self.streams_canceled

    def not_existed_anywhere(self, stream_id):
        return (
                not self.is_in_open(stream_id) and
                not self.is_in_processing(stream_id) and
                not self.is_in_completed(stream_id)
                )

    def is_in_open(self, stream_id: int) -> bool:
        return stream_id in self.streams_in_open.keys()

    def is_in_processing(self, stream_id: int) -> bool:
        return stream_id in self.streams_in_que.keys()

    def is_in_completed(self, stream_id: int) -> bool:
        return stream_id in self.closed_stream_ids

    def qsize_in_open(self) -> int:
        return len(self.streams_in_open)

    def qsize_in_processing(self) -> int:
        return len(self.streams_in_que)

    def total_qsize(self) -> int:
        return self.qsize_in_open() + self.qsize_in_processing()

    def cancel_stream(self, stream_id: int):
        self.streams_canceled.add(stream_id)

    def add_new_stream_in_open(self, stream_id: int, new_stream: Http2Stream):
        self.streams_in_open[stream_id] = new_stream

    def is_canceled_stream(self, stream_id: int):
        if stream_id in self.streams_canceled:
            del self.streams_in_que[stream_id]
            self.streams_canceled.remove(stream_id)
            return True
        return False

    def remove_stream_from_open(self, stream_id: int):
        if self.is_in_open(stream_id):
            del self.streams_in_open[stream_id]

    def maybe_closed_que_overflows(self):
        if len(self.closed_stream_ids) >= Http2StreamQueue.COMPLETED_QUE_SIZE:
            stream_id = self.closed_stream_ids_deque.popleft()
            self.closed_stream_ids.remove(stream_id)

    async def add_new_stream_in_processing(self, stream_id: int, stream: Http2Stream):
        self.streams_in_que[stream_id] = stream
        await self.streams.put(stream)

    def add_closed_stream(self, stream_id: int):
        self.maybe_closed_que_overflows()
        self.closed_stream_ids_deque.append(stream_id)
        self.closed_stream_ids.add(stream_id)
        try:
            del self.streams_in_que[stream_id]
        except Exception:
            pass

    def update_stream_in_open(self, stream_id: int, stream: Http2Stream):
        self.streams_in_open[stream_id] = stream

    def has_been_closed(self, stream_id: int) -> bool:
        return stream_id in self.closed_stream_ids or stream_id in self.streams_in_que.keys()

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


class TerminateAwareAsyncioQue:

    TERM_SIGNAL = 'TERMINATE' + uuid.uuid1().hex
    INIT = 'INIT'
    CLOSED = 'CLOSED'

    def __init__(self):
        self.que: asyncio.Queue = asyncio.Queue()
        self.state = TerminateAwareAsyncioQue.INIT

    def should_terminate(self, data: Union[Http2Stream, str, int]) -> bool:
        if isinstance(data, str) and data == TerminateAwareAsyncioQue.TERM_SIGNAL:
            self.state = TerminateAwareAsyncioQue.CLOSED
        return self.state == TerminateAwareAsyncioQue.CLOSED

    async def send_term_signal(self) -> None:
        await self.que.put(TerminateAwareAsyncioQue.TERM_SIGNAL)

    async def get(self) -> Http2Stream | str | int:
        return await self.que.get()

    async def put(self, data: Union[Http2Stream, int]) -> None:
        await self.que.put(data)


class AsyncGenerator:

    def __init__(self, streams: TerminateAwareAsyncioQue):
        self.streams = streams
        self._closing = False

    async def __aiter__(self):
        while True:
            data = await self.streams.get()
            # https://stackoverflow.com/questions/60226557/how-to-forcefully-close-an-async-generator
            # We cannot close async generator forcely.
            if self.streams.should_terminate(data):
                break
            yield data
