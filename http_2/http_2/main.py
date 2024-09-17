import asyncio
from server import Server, AsyncServerExecutor
from ssl_object import SSLConfig
from generic_http_object import GenericHttpRequest, GenericHttpResponse
from status_code import StatusCode

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

    executor = AsyncServerExecutor()
    executor.add_server(http_localhost_server)
    executor.add_server(localhost_server)
    executor.add_server(example_com_server)

    async with executor:
        await executor.execute_forever()

if __name__ == '__main__':
    asyncio.run(main())
