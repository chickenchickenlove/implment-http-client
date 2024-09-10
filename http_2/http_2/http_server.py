import asyncio

from data_structure import Trie
from client_reader import ClientReader, ClientWriter
from asyncio.streams import StreamReader, StreamWriter
from typing import Callable
from request_response_object import HttpRequest, HttpResponse
from status_code import StatusCode

# https://www.rfc-editor.org/rfc/rfc9110.html

# curl localhost:8080 -H "HELLO: 1" -H "BALLO: 2" -H "CALLO=1"
K = b'GET / HTTP/1.1\r\nHost: localhost:8080\r\nUser-Agent: curl/8.9.1\r\nAccept: */*\r\n\r\n'
Q = b'GET / HTTP/1.1\r\nHost: localhost:8080\r\nUser-Agent: curl/8.9.1\r\nAccept: */*\r\nHELLO: 123\r\n\r\n'
W = b'GET / HTTP/1.1\r\nHost: localhost:8080\r\nUser-Agent: curl/8.9.1\r\nAccept: */*\r\nHELLO: 1\r\nBALLO: 2\r\n\r\n'
W1 = b'POST / HTTP/1.1\r\nHost: localhost:8080\r\nUser-Agent: curl/8.9.1\r\nAccept: */*\r\nHELLO: 1\r\nBALLO: 2\r\nContent-Length: 15\r\nContent-Type: application/x-www-form-urlencoded\r\n\r\n123123123123123'
W2 = b'POST / HTTP/1.1\r\nHost: localhost:8080\r\nUser-Agent: curl/8.9.1\r\nAccept: */*\r\nHELLO: 1\r\nBALLO: 2\r\n\r\n'
W3 = b'POST / HTTP/1.1\r\nHost: localhost:8080\r\nUser-Agent: curl/8.9.1\r\nAccept: */*\r\nHELLO: 1\r\nBALLO: 2\r\nContent-Length: 15\r\nContent-Type: application/x-www-form-urlencoded\r\n\r\n123123123123123'


class HttpServerDispatcher:

    URL_CONTEXT = {
        'GET': Trie(),
        'POST': Trie(),
        'DELETE': Trie(),
        'PUT': Trie(),
    }

    @property
    def url_context(self):
        return HttpServerDispatcher.URL_CONTEXT

    def should_keep_alive(self, http_request: HttpRequest):
        if http_request.http_version == 'HTTP/1.1':
            return True
        if (http_request.http_version == 'HTTP/1' and
                http_request.headers.get('Connection') and
                http_request.headers.get('Connection') == 'keep-alive'):
            return True
        return False

    async def handle_request(self,
                             http_request: HttpRequest):

        f = self.url_context.get(http_request.method).search(http_request.path)
        if f:
            http_response = HttpResponse(http_request, StatusCode.OK, {}, '')
            http_response = await f(http_request, http_response)
        else:
            http_response = HttpResponse(http_request, StatusCode.NOT_FOUND, {}, '')

        return http_response

    async def should_continue(self, client_reader: StreamReader, timeout: int = 0.1) -> bytes:
        try:
            coro = client_reader.read(1)
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            return b''

    async def __call__(self, client_reader: StreamReader, client_writer: StreamWriter):
        previous_data_from_buffer = b''
        while True:
            print(f'Socket information = {client_writer.transport.get_extra_info("socket")}')
            reader = ClientReader(client_reader)
            client_msg = await reader.read_message(previous_data_from_buffer)

            http_request = HttpRequest(client_msg)
            http_response = await self.handle_request(http_request)

            writer = ClientWriter(client_writer, http_response)
            await writer.write()

            previous_data_from_buffer = await self.should_continue(client_reader)
            if not previous_data_from_buffer or not self.should_keep_alive(http_request):
                client_writer.close()
                await client_writer.wait_closed()
                break

    @staticmethod
    def route(path: str, methods: list[str]) -> Callable:
        def decorator(func):
            for method in methods:
                HttpServerDispatcher.URL_CONTEXT.get(method).add(path, func)
            return func
        return decorator

    @staticmethod
    def get_mapping(path: str) -> Callable:
        return HttpServerDispatcher.route(path, ['GET'])

    @staticmethod
    def post_mapping(path: str) -> Callable:
        return HttpServerDispatcher.route(path, ['POST'])

    @staticmethod
    def put_mapping(path: str) -> Callable:
        return HttpServerDispatcher.route(path, ['PUT'])

    @staticmethod
    def delete_mapping(path: str) -> Callable:
        return HttpServerDispatcher.route(path, ['DELETE'])
