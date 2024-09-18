import base64
import hpack

from hyperframe.frame import SettingsFrame
from hyperframe.frame import HeadersFrame
from collections import deque


class UnknownProtocolException(Exception):
    pass


class NeedToChangeProtocolException(Exception):

    """
    # HTTP/1.1 Upgrade Request Formatting.
    GET / HTTP/1.1
    Host: server.example.com
    Connection: Upgrade, HTTP2-Settings
    Upgrade: h2c
    HTTP2-Settings: <base64url encoding of HTTP/2 SETTINGS payload>

    """

    def __init__(self,
                 method: str,
                 path: str,
                 headers: dict[str, str],
                 http2_settings_headers: str,
                 response_msg: bytes):

        self._method = method
        self._path = path
        self._headers = headers
        self._settings_headers = http2_settings_headers
        self._response_msg = response_msg
        self._frames = deque([])

        self._convert_to_http2_frame()

    @property
    def response_msg(self):
        return self._response_msg

    @property
    def next_frame(self):
        return self._frames.popleft()

    def has_next_frame(self):
        return len(self._frames) > 0

    def _convert_to_http2_frame(self) -> None:
        settings_frame = self._settings_frame()
        headers_frame = self._headers_frame()

        self._frames.append(settings_frame)
        self._frames.append(headers_frame)

    def _headers_frame(self) -> HeadersFrame:
        headers = {}

        # Pseudo headers first
        headers[':method'] = self._method
        headers[':path'] = self._path
        headers[':scheme'] = 'HTTP/2.0'

        for key, value in self._headers.items():
            if key.lower() == 'host':
                headers[':authority'] = value
            elif key.lower() in ['connection', 'upgrade']:
                continue
            else:
                headers[key.lower()] = value

        encoder = hpack.Encoder()
        encoded_headers = encoder.encode(headers.items())

        headers_frame = HeadersFrame(stream_id=1, data=encoded_headers)
        headers_frame.flags.add('END_HEADERS')
        headers_frame.flags.add('END_STREAM')
        return headers_frame

    # Client's Settings frame. need to be ack.
    def _settings_frame(self):
        frame = SettingsFrame(0)

        def parse_http2_settings(http2_settings: str):
            decoded_settings = base64.urlsafe_b64decode(http2_settings)
            # HTTP/2 SETTINGS 프레임 형식: 각 설정 항목은 6바이트(2바이트 ID + 4바이트 값)
            settings = {}
            for i in range(0, len(decoded_settings), 6):
                id_bytes = decoded_settings[i:i+2]
                setting_id = int.from_bytes(id_bytes, byteorder='big')

                value_bytes = decoded_settings[i+2:i+6]
                value = int.from_bytes(value_bytes, byteorder='big')

                settings[setting_id] = value

            return settings

        settings_dict = parse_http2_settings(self._settings_headers)

        # 설정 값들을 SettingsFrame에 추가
        for setting_id, setting_value in settings_dict.items():
            frame.settings[setting_id] = setting_value

        return frame
