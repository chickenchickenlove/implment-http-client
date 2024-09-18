from typing import Literal


class ProtocolChange:

    _HTTP1_TO_UPDATE_RESPONSE = b'HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\nUpgrade: h2c\r\n\r\n'

    @staticmethod
    def get_response_msg(cls, protocol: Literal['HTTP/2']):
        match cls, protocol:
            case Http1Request, 'HTTP/2':
                return ProtocolChange._HTTP1_TO_UPDATE_RESPONSE
            case _:
                return ProtocolChange._HTTP1_TO_UPDATE_RESPONSE
