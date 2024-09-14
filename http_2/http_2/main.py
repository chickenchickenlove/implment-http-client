import asyncio
from server import HttpServerDispatcher
from generic_http_object import GenericHttpRequest, GenericHttpResponse
from status_code import StatusCode

@HttpServerDispatcher.route(path='/hello/ballo', methods=['POST', 'GET'])
async def return_ok(http_request: GenericHttpRequest, http_response: GenericHttpResponse):
    print('return_ok called.')
    http_response.status_code = StatusCode.OK
    http_response.body = 2
    return http_response

@HttpServerDispatcher.request_mapping(path='/')
async def return_ok(http_request: GenericHttpRequest, http_response: GenericHttpResponse):
    print('default function called. return 10')
    http_response.status_code = StatusCode.OK
    http_response.body = 3
    return http_response

@HttpServerDispatcher.get_mapping(path='/hello/ballo/my-test')
async def my_test(http_request: GenericHttpRequest, http_response: GenericHttpResponse):

    print('my_test_called.')
    http_response.status_code = StatusCode.OK
    return http_response


async def main():
    http_server = await asyncio.start_server(HttpServerDispatcher(), '127.0.0.1', 8080)
    async with http_server:
        await asyncio.gather(http_server.serve_forever())

if __name__ == '__main__':
    asyncio.run(main())
