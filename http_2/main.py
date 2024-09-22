import asyncio
import time

from http_2.server import Server, AsyncServerExecutor
from http_2.ssl_object import SSLConfig

from http_2.public.response import StreamingResponse, HttpResponse
from http_2.public.request import HttpRequest
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

    @http_localhost_server.get_mapping(path='/sse')
    @example_com_server.route(path='/sse', methods=['POST', 'GET'])
    @localhost_server.route(path='/sse', methods=['POST', 'GET'])
    async def sse(http_request: HttpRequest, http_response: HttpResponse):
        async def gen_events():
            for _ in range(5):
                await asyncio.sleep(1)
                yield f"data: 현재 시간은 {time.strftime('%Y-%m-%d %H:%M:%S')}\n"

        return StreamingResponse(gen_events())

    @http_localhost_server.get_mapping(path='/common')
    @example_com_server.route(path='/common', methods=['POST', 'GET'])
    @localhost_server.route(path='/common', methods=['POST', 'GET'])
    async def common(http_request: HttpRequest, http_response: HttpResponse) -> HttpResponse:
        return HttpResponse(body='hello')

    @http_localhost_server.get_mapping(path='/')
    @example_com_server.route(path='/', methods=['POST', 'GET'])
    @localhost_server.route(path='/', methods=['POST', 'GET'])
    async def common(http_request: HttpRequest, http_response: HttpResponse) -> HttpResponse:
        return HttpResponse(body='1')

    executor = AsyncServerExecutor()
    executor.add_server(http_localhost_server)
    executor.add_server(localhost_server)
    executor.add_server(example_com_server)

    async with executor:
        await executor.execute_forever()

if __name__ == '__main__':
    asyncio.run(main())
