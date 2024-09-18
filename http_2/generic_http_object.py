import base64

from hyperframe.frame import SettingsFrame
from typing import Union, Optional, Literal, Any

from status_code import StatusCode
from http2_object import Http2Stream


class Http1Request:
    def __init__(self, msg_dict: dict[str, Union[str, dict]]):
        if 'method' in msg_dict.keys():
            self._method: str = msg_dict['method']
        if 'uri' in msg_dict.keys():
            self._uri: str = msg_dict['uri']
        if 'http_version' in msg_dict.keys():
            self._http_version: str = msg_dict['http_version']
        if 'headers' in msg_dict.keys():
            self._headers: dict[str, Union[str, dict]] = msg_dict['headers']
        if 'body' in msg_dict.keys():
            self._body: str = msg_dict['body']

    @property
    def method(self):
        return self._method

    @property
    def uri(self):
        return self._uri

    @property
    def http_version(self):
        return self._http_version

    @property
    def headers(self):
        return self._headers

    @property
    def body(self):
        return self._body

    @property
    def path(self):
        return self._uri.split('?')[0]

    @property
    def query_params(self):
        query_params_dict = {}
        # http://example.com/path?key1=value1&key2=value2
        if len(self._uri.split('?')) > 1:
            query_param_string = self._uri.split('?')[1]
            for query_param in query_param_string.split('&'):
                k, v = query_param.split('=')
                query_params_dict[k] = v
        return query_params_dict


class Http1Response:

    @staticmethod
    def init_http1_response():
        return Http1Response(StatusCode.OK, {}, '')

    def __init__(self,
                 status_code: StatusCode,
                 headers: dict[str, Union[any, str]],
                 body: str):

        self._status_code = status_code
        self._headers = headers
        self._body = body

    @property
    def status_code(self):
        return self._status_code

    @status_code.setter
    def status_code(self, status_code: StatusCode):
        self._status_code = status_code

    @property
    def headers(self):
        return self._headers

    def update_headers(self, header: dict):
        self._headers.update(header)

    @property
    def body(self):
        return self._body

    @body.setter
    def body(self, body: str):
        self._body = str(body)


class Http2Request:

    def __init__(self, stream: Http2Stream):
        self._headers: dict[str, str] = stream.headers
        self._body: str = stream.body
        self._method: str = stream.headers.get('method')
        self._host: str = stream.headers.get('host')
        self._protocol: str = stream.headers.get('protocol')
        self._path: str = stream.headers.get('path')
        self._stream: Http2Stream = stream

    @property
    def headers(self):
        return self._headers

    @property
    def body(self):
        return self._body

    @property
    def method(self):
        return self._method

    @property
    def host(self):
        return self._host

    @property
    def protocol(self):
        return self._protocol

    @property
    def path(self):
        return self._path

    @property
    def stream(self):
        return self._stream


class Http2Response:

    PSEUDO_HEADERS = [':method', ':path', ':scheme', ':authority']

    def __init__(self,
                 status_code: int,
                 headers: dict[str, str],
                 body: Optional[str]
                 ):

        self.validate_headers(headers)
        self.response_headers = {':status': status_code}

        for key, value in headers.items():
            self.response_headers[key.lower()] = value.lower()

        self.body: Optional[str] = None
        if body:
            self.body = str(body)
            self.response_headers['content-length'] = len(self.body)
            self.response_headers['content-type'] = 'plain/text'


    def validate_headers(self, headers: dict[str, str]):
        for key in headers.keys():
            if key.startswith(':') and key not in Http2Response.PSEUDO_HEADERS:
                raise RuntimeError('fInvalid HTTP/2 Response header name. header name : {key}')


class GenericHttpRequest:

    def __init__(
            self,
            original_request: Http1Request | Http2Request,
            attributes: dict[str, str | dict]):

        self._original_request = original_request
        self._method = None
        self._uri = None
        self._http_version = None
        self._headers = None
        self._body = None

        if 'method' in attributes.keys():
            self._method: str = attributes['method']
        if 'path' in attributes.keys():
            self._uri: str = attributes['path']
        if 'http_version' in attributes.keys():
            self._http_version: str = attributes['http_version']
        if 'headers' in attributes.keys():
            self._headers: dict[str, Union[str, dict]] = attributes['headers']
        if 'body' in attributes.keys():
            self._body: str = attributes['body']

    @property
    def method(self):
        return self._method

    @property
    def uri(self):
        return self._uri

    @property
    def http_version(self):
        return self._http_version

    @property
    def headers(self):
        return self._headers

    @property
    def body(self):
        return self._body

    @property
    def path(self):
        return self._uri.split('?')[0]

    @property
    def query_params(self):
        query_params_dict = {}
        # http://example.com/path?key1=value1&key2=value2
        if len(self._uri.split('?')) > 1:
            query_param_string = self._uri.split('?')[1]
            for query_param in query_param_string.split('&'):
                k, v = query_param.split('=')
                query_params_dict[k] = v
        return query_params_dict

    @property
    def original_request(self) -> Http2Request | Http1Request:
        return self._original_request


class GenericHttpResponse:

    def __init__(self,
                 status_code: StatusCode,
                 headers: dict[str, Union[any, str]],
                 body: str):

        self._status_code = status_code
        self._headers = headers
        self._body = str(body)


    @property
    def status_code(self):
        return self._status_code

    @status_code.setter
    def status_code(self, status_code: StatusCode):
        self._status_code = status_code

    @property
    def headers(self):
        return self._headers

    def update_headers(self, header: dict):
        self._headers.update(header)

    @property
    def body(self):
        return self._body

    @body.setter
    def body(self, body: str):
        self._body = body


class Http2ToGenericHttpRequestConverter:

    @staticmethod
    def convert(original_request: Http2Request) -> GenericHttpRequest:
        attributes = {
            'headers': original_request.headers,
            'body': original_request.body,
            'host': original_request.host,
            'path': original_request.path,
            'method': original_request.method
        }

        return GenericHttpRequest(original_request, attributes)


class GenericHttpToHttp2ResponseConverter:

    @staticmethod
    def convert(original_response: GenericHttpResponse) -> Http2Response:
        return Http2Response(
            original_response.status_code.status_code,
            original_response.headers,
            original_response.body
        )




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
