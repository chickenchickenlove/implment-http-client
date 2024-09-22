from http_2.internal.http2_request import Http2Request
from http_2.public.request import HttpRequest


class Http2RequestToHttpRequestConverter:

    @staticmethod
    def convert(original_request: Http2Request) -> HttpRequest:
        attributes = {
            'headers': original_request.headers,
            'body': original_request.body,
            'host': original_request.host,
            'path': original_request.path,
            'method': original_request.method,
            'protocol': original_request.headers.get('protocol')
        }

        return HttpRequest(original_request, attributes)
