from typing import Union

from http_2.type.http_object import HeaderType, QueryParamsType
from http_2.internal.interface_request import Request


class Http1Request(Request):

    def __init__(self,
                 msg_dict: dict[str, Union[str, dict]]):
        if 'method' in msg_dict.keys():
            self._method: str = msg_dict['method']
        if 'uri' in msg_dict.keys():
            self._uri: str = msg_dict['uri']
        if 'http_version' in msg_dict.keys():
            self._protocol: str = msg_dict['http_version']
        if 'headers' in msg_dict.keys():
            self._headers: dict[str, Union[str, dict]] = msg_dict['headers']
        if 'body' in msg_dict.keys():
            self._body: str = msg_dict['body']

    @property
    def method(self) -> str:
        return self._method

    @property
    def uri(self) -> str:
        return self._uri

    @property
    def protocol(self) -> str:
        return self._protocol

    @property
    def headers(self) -> HeaderType:
        return self._headers

    @property
    def body(self) -> str:
        return self._body

    @property
    def path(self) -> str:
        return self._uri.split('?')[0]

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
