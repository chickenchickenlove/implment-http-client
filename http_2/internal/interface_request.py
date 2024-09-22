from abc import abstractmethod, ABC

from http_2.type.http_object import HeaderType, QueryParamsType


class Request(ABC):

    @property
    @abstractmethod
    def method(self) -> str:
        pass

    @property
    @abstractmethod
    def uri(self) -> str:
        pass

    @property
    @abstractmethod
    def protocol(self) -> str:
        pass

    @property
    @abstractmethod
    def headers(self) -> HeaderType:
        pass

    @property
    @abstractmethod
    def body(self) -> str:
        pass

    @property
    @abstractmethod
    def path(self) -> str:
        pass

    @property
    @abstractmethod
    def query_params(self) -> QueryParamsType:
        pass
