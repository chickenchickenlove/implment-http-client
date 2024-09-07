
import asyncio

from client_reader import ClientReader
from asyncio.streams import StreamReader, StreamWriter
from typing import Callable

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
        'GET': {},
        'POST': {},
        'DELETE': {},
        'PUT': {},
    }

    @property
    def url_context(self):
        return HttpServerDispatcher.URL_CONTEXT

    async def __call__(self,
                       client_reader: StreamReader,
                       client_writer: StreamWriter):
        reader = ClientReader(client_reader)
        client_msg = await reader.read_message()

        method = client_msg.get('method')
        url = client_msg.get('uri')

        f = self.url_context.get(method).get(url)
        r = await f(client_msg)
        print(r)

    @staticmethod
    def route(url: str, methods: list[str]) -> Callable:
        def decorator(func):
            for method in methods:
                HttpServerDispatcher.URL_CONTEXT.get(method)[url] = func
            return func
        return decorator


@HttpServerDispatcher.route(url='/hello/ballo', methods=['POST', 'GET'])
async def my_function(client_dict: dict[str, str]):
    print(client_dict)
    # print(client_dict)


async def main():
    http_server = await asyncio.start_server(HttpServerDispatcher(), '127.0.0.1', 8080)

    # async context manager -> 소켓이 닫힐 때까지 기다림.
    async with http_server:
        await asyncio.gather(http_server.serve_forever())


if __name__ == '__main__':
    asyncio.run(main())

'''

A message is considered "complete" when all of the octets indicated by its framing are available. 
Note that, when no explicit framing is used, a response message that is ended by the underlying connection's close 
is considered complete even though it might be indistinguishable from an incomplete response, unless a transport-level error 
indicates that it is not complete.


Messages start with control data that describe its primary purpose. Request message control data includes a request method (Section 9), request target (Section 7.1), and protocol version (Section 2.5). Response message control data includes a status code (Section 15), optional reason phrase, and protocol version.

'''
