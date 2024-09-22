from abc import abstractmethod, ABC


class Response(ABC):

    @property
    @abstractmethod
    def protocol(self):
        pass

    @property
    @abstractmethod
    def status_code(self):
        pass

    @property
    @abstractmethod
    def headers(self):
        pass

    @property
    @abstractmethod
    def body(self):
        pass

    @abstractmethod
    def has_body(self):
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
