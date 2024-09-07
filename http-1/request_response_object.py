from typing import Union


class HttpRequest:

    def __init__(self, msg_dict: dict[str, Union[str, dict]]):
        self._method = msg_dict['method']


        msg_dict = {
            'method': http_method,
            'uri': uri,
            'http_version': http_version,
            'headers': headers,
            'body': body
        }

    @property
    def method(self):
        return self._method
