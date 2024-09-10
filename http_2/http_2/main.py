import asyncio
from http_server import HttpServerDispatcher
from request_response_object import HttpRequest, HttpResponse
from status_code import StatusCode

@HttpServerDispatcher.route(path='/hello/ballo', methods=['POST', 'GET'])
async def my_function(http_request: HttpRequest, http_response: HttpResponse):
    http_response.status_code = StatusCode.OK
    return http_response


@HttpServerDispatcher.get_mapping(path='/hello/ballo/my-test')
async def my_test(http_request: HttpRequest, http_response: HttpResponse):
    # print(f'my_test called. '
    #       f'{http_request.http_version=}\n'
    #       f'{http_request.headers=}\n'
    #       f'{http_request.uri=}\n'
    #       f'{http_request.query_params=}')

    http_response.status_code = StatusCode.OK
    return http_response


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
