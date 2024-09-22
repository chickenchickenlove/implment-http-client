from typing import Union

from http_2.internal.interface_request import Request
from http_2.internal.http1_request import Http1Request
from http_2.internal.http2_request import Http2Request


class HttpRequest(Request):

    def __init__(
            self,
            original_request: Http1Request | Http2Request,
            attributes: dict[str, str | dict]):

        self._original_request = original_request
        self._method = None
        self._uri = None
        self._protocol = None
        self._headers = None
        self._body = None

        if 'method' in attributes.keys():
            self._method: str = attributes['method']
        if 'path' in attributes.keys():
            self._uri: str = attributes['path']
        if 'protocol' in attributes.keys():
            self._protocol: str = original_request.protocol
        if 'headers' in attributes.keys():
            self._headers: dict[str, Union[str, dict]] = attributes['headers']
        if 'body' in attributes.keys():
            self._body: str = attributes['body']

    @property
    def protocol(self) -> str:
        return self._protocol

    @property
    def method(self):
        return self._method

    @property
    def uri(self):
        return self._uri

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
