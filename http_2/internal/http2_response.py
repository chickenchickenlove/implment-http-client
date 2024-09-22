from http_2.status_code import StatusCode
from http_2.internal.interface_response import Response

from http_2.type.http_object import HeaderType
from http_2.constant.protocol import HTTP2


class Http2Response(Response):

    PSEUDO_HEADERS = [':method', ':path', ':scheme', ':authority']

    def __init__(self,
                 status_code: StatusCode,
                 headers: HeaderType,
                 body: str = ''
                 ):

        self.validate_headers(headers)

        self._protocol = HTTP2
        self._status_code = status_code
        self._headers = {}
        self._body = body

        self._headers[':status'] = str(status_code.status_code)

        for key, value in headers.items():
            self._headers[key.lower()] = str(value).lower()

        if body:
            self._body = str(body)
            self._headers['content-length'] = str(len(self._body))
            self._headers['content-type'] = 'plain/text'

    def validate_headers(self, headers: dict[str, str]):
        for key in headers.keys():
            if key.startswith(':') and key not in Http2Response.PSEUDO_HEADERS:
                raise RuntimeError('fInvalid HTTP/2 Response header name. header name : {key}')

    @property
    def protocol(self):
        return self._protocol

    @property
    def status_code(self):
        return self._status_code

    @property
    def headers(self):
        print('here')
        return self._headers

    @property
    def body(self):
        return self._body

    def has_body(self):
        return len(self._body) > 0
