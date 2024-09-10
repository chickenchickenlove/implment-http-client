from typing import Union
from status_code import StatusCode

# https://developer.mozilla.org/ko/docs/Web/HTTP/Messages

class HttpRequest:

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


class HttpResponse:

    def __init__(self,
                 http_request: HttpRequest,
                 status_code: StatusCode,
                 headers: dict[str, Union[any, str]],
                 body: str):

        self._http_request = http_request
        self._status_code = status_code
        self._headers = headers
        self._body = body

    @property
    def http_request(self):
        return self._http_request

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
