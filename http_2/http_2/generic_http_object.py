from typing import Union, Optional
from status_code import StatusCode
from http2_object import Http2Stream


class Http1Request:
    pass


class Http1Response:
    pass


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
        self.response_headers = []

        self.response_headers.append((':status', status_code))
        for key, value in headers.items():
            header = (key.lower(), value.lower())
            self.response_headers.append(header)

        self.body: Optional[str] = None
        if body:
            self.body = str(body)

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


# class Http1ToGenericHttpRequestConverter:
#
#     @staticmethod
#     def convert(original_request: Http21equest) -> GenericHttpRequest:
#
#         pass
