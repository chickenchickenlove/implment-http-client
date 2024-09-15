import asyncio
from server import HttpServerDispatcher, Server
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
    server = Server(host='0.0.0.0', port=8080)
    await server.serve_forever()

if __name__ == '__main__':
    asyncio.run(main())
