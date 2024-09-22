from abc import ABC, abstractmethod
from typing import Any, cast

from http_2.internal.interface_request import Request
from http_2.internal.http1_request import Http1Request
from http_2.internal.http2_request import Http2Request


class ParameterStore:

    def __init__(self):
        self._params = {}
        self._params_by_type: dict[type, dict[str, Any]] = cast(dict[type, dict[str, Any]], {})

    def find_param(self, param_name: str) -> Any | None:
        return self._params.get(param_name, None)

    def find_param_with_type(self, param_name: str, param_type: type) -> Any | None:
        if param_type in self._params_by_type.keys():
            return self._params_by_type[param_type].get(param_name, None)
        return None

    def add_param(self, param_name: str, value: Any) -> None:
        param_type = type(value)
        self._params[param_name] = value
        if param_type not in self._params_by_type.keys():
            self._params_by_type[param_type] = {}

        self._params_by_type.get(param_type)[param_name] = value


class ConnectionContext(ABC):

    @abstractmethod
    def find_param(self, param_name: str) -> Any | None:
        pass

    @abstractmethod
    def find_param_with_type(self, param_name: str, param_type: type) -> Any | None:
        pass

    @abstractmethod
    def add_param(self, param_name: str, value: Any) -> None:
        pass


class HTTP1ConnectionContext(ConnectionContext):

    def __init__(self, connection):
        self._connection = connection

        self._store = ParameterStore()
        self.add_param('connection', connection)

    def find_param(self, param_name: str) -> Any | None:
        return self._store.find_param(param_name)

    def find_param_with_type(self, param_name: str, param_type: type) -> Any | None:
        return self._store.find_param_with_type(param_name, param_type)

    def add_param(self, param_name: str, value: Any) -> None:
        self._store.add_param(param_name, value)


class HTTP2ConnectionContext(ConnectionContext):

    def __init__(self, connection):
        self._request = connection

        self._store = ParameterStore()
        self.add_param('connection', connection)

    def find_param(self, param_name: str) -> Any | None:
        return self._store.find_param(param_name)

    def find_param_with_type(self, param_name: str, param_type: type) -> Any | None:
        return self._store.find_param_with_type(param_name, param_type)

    def add_param(self, param_name: str, value: Any) -> None:
        self._store.add_param(param_name, value)


class RequestContext(ABC):

    @property
    @abstractmethod
    def request(self) -> Request:
        pass

    @abstractmethod
    def find_param(self, param_name: str) -> Any | None:
        pass

    @abstractmethod
    def find_param_with_type(self, param_name: str, param_type: type) -> Any | None:
        pass

    @abstractmethod
    def add_param(self, param_name: str, value: Any) -> None:
        pass


class HTTP1RequestContext(RequestContext):

    def __init__(self, request):
        self._request = request
        self._store = ParameterStore()
        self.add_param('http_request', request)

    @property
    def request(self) -> Http1Request:
        return self._request

    def find_param(self, param_name: str) -> Any | None:
        return self._store.find_param(param_name)

    def find_param_with_type(self, param_name: str, param_type: type) -> Any | None:
        return self._store.find_param_with_type(param_name, param_type)

    def add_param(self, param_name: str, value: Any):
        self._store.add_param(param_name, value)

class HTTP2RequestContext(RequestContext):

    def __init__(self, stream):
        self._stream = stream
        self._request = None

        self._store = ParameterStore()
        self.add_param('stream', stream)


    @property
    def request(self) -> Http2Request:
        return self._request

    @request.setter
    def request(self, request) -> None:
        self._request = request

    def find_param(self, param_name: str) -> Any | None:
        return self._store.find_param(param_name)

    def find_param_with_type(self, param_name: str, param_type: type) -> Any | None:
        return self._store.find_param_with_type(param_name, param_type)

    def add_param(self, param_name: str, value: Any):
        self._store.add_param(param_name, value)
