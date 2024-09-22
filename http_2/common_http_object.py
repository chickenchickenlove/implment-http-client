import base64

from hyperframe.frame import SettingsFrame
from typing import Literal


class NeedtoResponseException(Exception):

    def __init__(self, msg: str, response_code: int):
        self.msg = msg
        self.response_code = response_code


class NeedToChangeProtocol:

    HTTP2 = 'HTTP/2'
    HTTP1_TO_UPDATE_RESPONSE = b'HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\nUpgrade: h2c\r\n\r\n'

    def __init__(self, protocol: Literal['HTTP/2'], init_val: str):
        self._protocol = protocol
        self._init_val = init_val
        self._error = None

        self.is_valid_request()


    def is_valid_request(self) -> bool:
        match self._protocol:
            case NeedToChangeProtocol.HTTP2:
                try:
                    self._init_val = self._parse_http2_frame()
                    return True
                except Exception as e:
                    return False
            case _:
                raise False

    @property
    def protocol(self):
        return self._protocol

    @property
    def init_val(self):
        return self._init_val

    @property
    def error(self):
        return self._error

    def get_response_msg(self, cls, protocol: Literal['HTTP/2']):
        match cls, protocol:
            case Http1Request, 'HTTP/2':
                return NeedToChangeProtocol.HTTP1_TO_UPDATE_RESPONSE
            case _:
                return NeedToChangeProtocol.HTTP1_TO_UPDATE_RESPONSE

    '''
    SETTINGS Frame {
      Length (24),
      Type (8) = 0x04,

      Unused Flags (7),
      ACK Flag (1),

      Reserved (1),
      Stream Identifier (31) = 0,

      Setting (48) ...,
    }

    Setting {
      Identifier (16), (2 bytes)
      Value (32), (4 bytes)
    }
    '''
    def _parse_http2_frame(self):
        def parse_http2_settings(http2_settings: str) -> dict:
            decoded_settings = base64.urlsafe_b64decode(http2_settings)

            # HTTP/2 SETTINGS Frame Format: Id : 2bytes, value: 4bytes
            settings = {}
            for i in range(0, len(decoded_settings), 6):
                id_bytes = decoded_settings[i:i+2]
                setting_id = int.from_bytes(id_bytes, byteorder='big')

                value_bytes = decoded_settings[i+2:i+6]
                value = int.from_bytes(value_bytes, byteorder='big')

                settings[setting_id] = value
            return settings

        def build_settings_frame_with_hyperframe(settings):
            frame = SettingsFrame(0)

            for setting_id, setting_value in settings.items():
                frame.settings[setting_id] = setting_value

            return frame

        decoded_settings = parse_http2_settings(self.init_val)
        return build_settings_frame_with_hyperframe(decoded_settings)
