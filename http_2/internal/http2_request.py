from http_2.http2_object import Http2Stream
from http_2.type.http_object import HeaderType, QueryParamsType
from http_2.internal.interface_request import Request


class Http2Request(Request):

    def __init__(self, stream: Http2Stream):
        self._headers: dict[str, str] = stream.headers
        self._body: str = stream.body
        self._method: str = stream.headers.get('method')
        self._host: str = stream.headers.get('host')
        self._protocol: str = stream.headers.get('protocol')
        # uri : Path + Query Parameters
        self._uri: str = stream.headers.get('path')
        self._stream: Http2Stream = stream

    @property
    def headers(self) -> HeaderType:
        return self._headers

    @property
    def body(self) -> str:
        return self._body

    @property
    def method(self) -> str:
        return self._method

    @property
    def host(self) -> str:
        return self._host

    @property
    def protocol(self):
        return self._protocol

    @property
    def path(self):
        return self._uri.split('?')[0]

    @property
    def stream(self):
        return self._stream

    @property
    def uri(self) -> str:
        return self._uri

    @property
    def query_params(self) -> QueryParamsType:
        query_params_dict = {}
        # http://example.com/path?key1=value1&key2=value2
        if len(self._uri.split('?')) > 1:
            query_param_string = self._uri.split('?')[1]
            for query_param in query_param_string.split('&'):
                k, v = query_param.split('=')
                query_params_dict[k] = v
        return query_params_dict





# class GenericHttpToHttp2ResponseConverter:
#
#     @staticmethod
#     def convert(original_response: GenericHttpResponse) -> Http2Response:
#         return Http2Response(
#             original_response.status_code.status_code,
#             original_response.headers,
#             original_response.body
#         )
