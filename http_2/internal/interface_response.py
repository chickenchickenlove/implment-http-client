from typing import Literal

from abc import abstractmethod, ABC
from http_2.type.http_object import HeaderType
from http_2.status_code import StatusCode

class Response(ABC):

    @property
    @abstractmethod
    def protocol(self) -> Literal['HTTP/1', 'HTTP/1.1', 'HTTP/2']:
        pass

    @property
    @abstractmethod
    def status_code(self) -> StatusCode:
        pass

    @property
    @abstractmethod
    def headers(self) -> HeaderType:
        pass

    @property
    @abstractmethod
    def body(self) -> str:
        pass

    @abstractmethod
    def has_body(self) -> bool:
        pass


class AbstractStreamingResponse(Response):

    @abstractmethod
    async def next_response(self):
        pass

    @property
    @abstractmethod
    def contents_generator(self):
        pass

    @property
    @abstractmethod
    def media_type(self):
        pass

    @property
    @abstractmethod
    def char_set(self):
        pass
