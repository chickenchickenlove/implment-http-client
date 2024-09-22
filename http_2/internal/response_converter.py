from abc import ABC, abstractmethod

from typing import Literal

from http_2.type.http_object import HeaderType
from http_2.public.response import HttpResponse, StreamingResponse
from http_2.internal.interface_response import Response
from http_2.internal.http1_response import Http1Response, Http1StreamingResponse
from http_2.internal.http2_response import Http2Response

from http_2.constant.protocol import HTTP1_1, HTTP2

ConvertedResponse = Http1Response | Http2Response


class ResponseConverter(ABC):

    @abstractmethod
    def convert(self, response: Response) -> ConvertedResponse:
        pass


class HTTP1ResponseConverter(ResponseConverter):

    def convert(self, response: HttpResponse) -> Http1Response:
        return Http1Response(
            status_code=response.status_code,
            headers=response.headers,
            body=response.body
        )


class HTTP1StreamingResponseConverter(ResponseConverter):

    def convert(self, response: StreamingResponse) -> Http1StreamingResponse:
        return Http1StreamingResponse(
            contents_generator=response.contents_generator,
            status_code=response.status_code,
            headers=response.headers,
            media_type=response.media_type,
            char_set=response.char_set)


class HTTP2ResponseConverter(ResponseConverter):

    def convert(self, response: HttpResponse) -> Http2Response:
        return Http2Response(
            response.status_code,
            response.headers,
            response.body)


class NotImplementedResponseConverter(ResponseConverter):

    def convert(self, response: HttpResponse) -> Http2Response:
        raise NotImplementedError('Unexpected response type. please consider HTTPResponse or StreamingResponse instead.')


class ResponseConverterStore:

    def __init__(self):
        self._store = {
            HTTP1_1: HTTP1ResponseConverter(),
            HTTP2: HTTP2ResponseConverter(),
            'UNEXPECTED': NotImplementedResponseConverter(),
        }

        self._streaming_store = {
            HTTP1_1: HTTP1StreamingResponseConverter(),
            'UNEXPECTED': NotImplementedResponseConverter(),
        }

    def get_converter(self,
                      protocol: Literal['HTTP/1.1', 'HTTP/2'],
                      headers: HeaderType) -> ResponseConverter:

        content_type = ''
        for key in headers.keys():
            if key.lower() == 'content-type':
                content_type = headers[key]

        match content_type:
            case 'text/event-stream':
                return self._streaming_store.get(protocol)
            case 'text/plain':
                return self._store.get(protocol)
            case _:
                return self._store.get(protocol)


RESPONSE_CONVERTER_STORE = ResponseConverterStore()
