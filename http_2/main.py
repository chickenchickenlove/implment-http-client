import asyncio
import time

from http_2.server import Server, AsyncServerExecutor
from http_2.ssl_object import SSLConfig
from http_2.common_http_object import GenericHttpRequest, GenericHttpResponse
from http_2.http1_response import StreamingResponse, GeneralHttp1Response
from http_2.status_code import StatusCode

async def main():

    localhost_ssl_config = SSLConfig()
    localhost_ssl_config.add_tls_with_hostname(
        hostname='localhost',
        certfile_path='...',
        keyfile_path='...')

    example_com_ssl_config = SSLConfig()
    example_com_ssl_config.add_tls_with_hostname(
        hostname='example.com',
        certfile_path='...',
        keyfile_path='...')

    http_localhost_server = Server(8080)
    localhost_server = Server(443, hostname='localhost', ssl_config=localhost_ssl_config)
    example_com_server = Server(443, hostname='example.com', ssl_config=example_com_ssl_config)

    @http_localhost_server.route(path='/hello/ballo2', methods=['POST', 'GET'])
    @example_com_server.route(path='/hello/ballo', methods=['POST', 'GET'])
    @localhost_server.route(path='/hello/ballo', methods=['POST', 'GET'])
    async def return_ok(http_request: GenericHttpRequest, http_response: GenericHttpResponse):
        print('return_ok called.')
        http_response.status_code = StatusCode.OK
        http_response.body = 2
        return http_response

    # for the test.
    @http_localhost_server.route(path='/', methods=['POST', 'GET'])
    @example_com_server.route(path='/', methods=['POST', 'GET'])
    @localhost_server.route(path='/', methods=['POST', 'GET'])
    async def return_t(http_request: GenericHttpRequest, http_response: GenericHttpResponse):
        print('return_ok called.')
        http_response.status_code = StatusCode.OK
        http_response.body = 2
        return http_response

    @http_localhost_server.get_mapping(path='/sse')
    async def sse(http_request: GenericHttpRequest, http_response: GenericHttpResponse):
        async def gen_events():
            for _ in range(5):
                await asyncio.sleep(1)
                yield f"data: 현재 시간은 {time.strftime('%Y-%m-%d %H:%M:%S')}\n"

        return StreamingResponse(gen_events())

    @http_localhost_server.get_mapping(path='/common')
    async def common(http_request: GenericHttpRequest, http_response: GenericHttpResponse):
        return GeneralHttp1Response(body='hello')

    executor = AsyncServerExecutor()
    executor.add_server(http_localhost_server)
    executor.add_server(localhost_server)
    executor.add_server(example_com_server)

    async with executor:
        await executor.execute_forever()

if __name__ == '__main__':
    asyncio.run(main())
