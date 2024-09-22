from typing import AsyncIterable

from http_2.status_code import StatusCode

from http_2.type.http_object import HeaderType

from http_2.internal.interface_response import Response, AbstractStreamingResponse

from http_2.constant.protocol import HTTP1_1


class HttpResponse(Response):
    def __init__(self,
                 status_code: StatusCode = StatusCode.OK,
                 headers: HeaderType | None = None,
                 body: str = '',
                 ):

        self._status_code = status_code
        self._headers = {} if headers is None else headers
        self._body = body

    @property
    def protocol(self):
        return 'NOT_DETERMINED_YET'

    @property
    def status_code(self):
        return self._status_code

    @property
    def headers(self):
        return self._headers

    @property
    def body(self):
        return self._body

    def has_body(self):
        return len(self._body) > 0


class StreamingResponse(AbstractStreamingResponse):

    def __init__(self,
                 contents_generator: AsyncIterable,
                 status_code: StatusCode = StatusCode.OK,
                 headers: dict[str, str] | None = None,
                 media_type: str = 'text/event-stream',
                 char_set: str = 'utf-8'
                 ):

        self._body_iterator = contents_generator
        self._status_code = status_code
        self._headers = {} if headers is None else headers
        self._media_type = media_type
        self._char_set = char_set
        self._protocol = HTTP1_1
        self._encoding = 'utf-8'

        if media_type == 'text/event-stream':
            headers = {
                'Content-Type': 'text/event-stream',
                'Transfer-Encoding': 'chunked',
                'Cache-Control': 'no-cache'
            }
            self._headers.update(headers)

    async def next_response(self):
        async for chunk in self._body_iterator:
            return chunk
        return ''

    @property
    def protocol(self):
        return self._protocol

    @property
    def status_code(self):
        return self._status_code

    @property
    def encoding(self):
        return self._encoding

    @property
    def headers(self):
        return self._headers

    @property
    def body(self):
        raise NotImplemented('Not Implemented. because body is async generator')

    @property
    def has_body(self):
        raise NotImplemented('Not Implemented. because body is async generator')

    @property
    def contents_generator(self):
        return self._body_iterator

    @property
    def media_type(self):
        return self._media_type

    @property
    def char_set(self):
        return self._char_set
