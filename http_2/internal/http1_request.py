from http_2.type.http_object import HeaderType, QueryParamsType
from http_2.internal.interface_request import Request
from http_2.public.expect_continue_chains import CONTINUE_CHAINS


class Http1Request(Request):

    # uri : Path + Query Parameters
    def __init__(self,
                 method: str,
                 uri: str,
                 protocol: str,
                 headers: dict[str, str]):

        self._method = method
        self._uri = uri
        self._protocol = protocol
        self._headers = headers
        self._body = ''

        self._have_expect_header = 'expect' in headers.keys()

        self._100_continue = self._have_expect_header and headers['expect']
        self._100_continue_chains = CONTINUE_CHAINS


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

    @body.setter
    def body(self, contents: str):
        self._body = contents

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


    def expect_100_continue(self) -> bool:
        return self._have_expect_header

    # Chain raise error to change context switching.
    def execute_chains_100_continue(self) -> None:
        self._100_continue_chains.execute(self._method,
                                          self._uri,
                                          self._protocol,
                                          self._headers)
