import asyncio

from asyncio.streams import StreamReader, StreamWriter
from typing import Callable
from data_structure import Trie
from protocol_verifier import ProtocolVerifier

from http1_connection import Http1Connection
from http2_connection import Http2Connection
from generic_http_object import GenericHttpRequest, GenericHttpResponse
from status_code import StatusCode
from ssl_object import SSLConfig, IntegrateSSLConfig


class Server:

    def __init__(self, port: int, /, hostname: str = None, ssl_config: SSLConfig = None):
        self._host = '0.0.0.0'
        self._port = port

        self._ssl_config: SSLConfig | None = ssl_config
        self._hostname = hostname

        self._url_context = {
            'GET': Trie(),
            'POST': Trie(),
            'DELETE': Trie(),
            'PUT': Trie(),
            'HEAD': Trie(),
        }

    @property
    def port(self):
        return self._port

    @property
    def url_context(self):
        return self._url_context

    @property
    def ssl_config(self):
        return self._ssl_config

    @property
    def hostname(self):
        return self._hostname

    async def serve_forever(self):
        if self.ssl_config:
            ssl_context = self.ssl_config.default_ssl_context
            ssl_context.set_servername_callback(self.ssl_config.sni_callback)
            http_server = await asyncio.start_server(self.handle_request, self._host, self._port, ssl=ssl_context)
        else:
            http_server = await asyncio.start_server(self.handle_request, self._host, self._port)
        async with http_server:
            await asyncio.gather(http_server.serve_forever())

    async def _dispatch(self, http_request: GenericHttpRequest, http_response: GenericHttpResponse):
        path = http_request.path
        func = self._url_context.get(http_request.method).search(path)

        if not func:
            http_response.status_code = StatusCode.NOT_FOUND
            return http_request, http_response
        else:
            response = await func(http_request, http_response)
            return http_request, response


    async def handle_request(self, client_reader: StreamReader, client_writer: StreamWriter):
        try:
            protocol, first_line = await ProtocolVerifier.ensure_protocol(client_reader)
            match protocol:
                case 'HTTP/2':
                    connection = await Http2Connection.create(client_reader, client_writer, self._dispatch)
                    try:
                        async with asyncio.TaskGroup() as tg:
                            tg.create_task(connection.parse_http2_frame())
                            tg.create_task(connection.consume_complete_stream())
                    except Exception as e:
                        print(f'Unexpected Exception occurs. error : {e}')
                    pass
                case 'HTTP/1':
                    await Http1Connection(client_reader, client_writer, first_line).handle_request(self._dispatch)
                    pass
                case _:
                    print('UNKNOWN PROTOCOL')
        except Exception as e:
            print(f'handle request exception: {e}')
        finally:
            try:
                client_writer.close()
                await client_writer.wait_closed()
            except (BrokenPipeError, ConnectionResetError) as e:
                print(f'Client already closed connection.')
            except Exception as e:
                print(e)

    def route(self, path: str, methods: list[str]) -> Callable:
        def decorator(func):
            for method in methods:
                self._url_context.get(method).add(path, func)
            return func
        return decorator

    def request_mapping(self, path: str) -> Callable:
        return self.route(path, ['GET', 'POST', 'DELETE', 'PUT', 'HEAD'])

    def get_mapping(self, path: str) -> Callable:
        return self.route(path, ['GET'])

    def post_mapping(self, path: str) -> Callable:
        return self.route(path, ['POST'])

    def put_mapping(self, path: str) -> Callable:
        return self.route(path, ['PUT'])

    def delete_mapping(self, path: str) -> Callable:
        return self.route(path, ['DELETE'])

    @staticmethod
    async def graceful_shutdown(timeout: int):
        # TODO : NEED TO BE
        # await asyncio.sleep(timeout)
        # for task in asyncio.all_tasks():
        #     task.cancel()
        #     task.done()
        pass


class IntegratedServer:

    DEFAULT_SERVER = 'DEFAULT'

    def __init__(self,
                 port: int,
                 /,
                 hostname: str = '',
                 ssl_config: IntegrateSSLConfig = None):

        self._host = '0.0.0.0'
        self._port = port
        self._ssl_config = ssl_config
        self._servers: dict[str, Server] = {}

    @property
    def ssl_config(self):
        return self._ssl_config

    @ssl_config.setter
    def ssl_config(self, ssl_config: IntegrateSSLConfig):
        self._ssl_config = ssl_config

    def add_server(self, hostname: str, server: Server):
        if not self._servers.get(IntegratedServer.DEFAULT_SERVER):
            self._servers[IntegratedServer.DEFAULT_SERVER] = server
        self._servers[hostname] = server

    async def serve_forever(self):
        if self._ssl_config:
            ssl_context = self._ssl_config.default_ssl_context
            ssl_context.set_servername_callback(self._ssl_config.sni_callback)
            http_server = await asyncio.start_server(self.handle_request, self._host, self._port, ssl=ssl_context)
        else:
            http_server = await asyncio.start_server(self.handle_request, self._host, self._port)
        async with http_server:
            await asyncio.gather(http_server.serve_forever())

    def _find_sni(self, writer: StreamWriter):
        """
        The attribute 'sni' will be set up when
        ssl_object.IntegrateSSLConfig.sni_callback() is called.
        """
        if (obj := writer.get_extra_info('ssl_object')) and hasattr(obj, 'sni'):
            return obj.sni
        return ''

    async def handle_request(self, client_reader: StreamReader, client_writer: StreamWriter):
        sni = self._find_sni(client_writer)
        if sni:
            server = self._servers.get(sni)
        else:
            server = self._servers.get(IntegratedServer.DEFAULT_SERVER)

        if not server:
            client_writer.close()
            await client_writer.wait_closed()
            return

        await server.handle_request(client_reader, client_writer)


class AsyncServerExecutor:

    def __init__(self):
        self.servers = []
        self.tasks: list[asyncio.Task] = []

        self.port_to_server: dict[int, list[Server]] = {}
        self.integrated_servers = []

    def add_server(self, server: Server):
        if not self.port_to_server.get(server.port):
            self.port_to_server[server.port] = []
        self.port_to_server[server.port].append(server)

    async def execute_forever(self):
        for integrated_server in self.integrated_servers:
            # t1 = asyncio.create_task(integrated_server.serve_forever())
            self.tasks.append(asyncio.create_task(integrated_server.serve_forever()))
        await asyncio.gather(*self.tasks)

    def _composite_ssl_config(self,
                              integrated_server: IntegratedServer,
                              integrated_ssl_config: IntegrateSSLConfig,
                              server):

        integrated_server.add_server(server.hostname, server)
        if not server.ssl_config:
            return

        # Set ssl context
        each_ssl_config = server.ssl_config
        if each_ssl_config.default_ssl_context:
            integrated_ssl_config.default_ssl_context = each_ssl_config.default_ssl_context

        integrated_ssl_config.ssl_handshake_timeout = each_ssl_config.ssl_handshake_timeout
        integrated_ssl_config.ssl_shutdown_timeout = each_ssl_config.ssl_shutdown_timeout
        integrated_server.ssl_config = integrated_ssl_config

        for hostname, ssl_context in each_ssl_config.ssl_context_store.store.items():
            integrated_ssl_config.add_tls_with_hostname(hostname, ssl_context)
            if not integrated_ssl_config.default_ssl_context:
                integrated_ssl_config.default_ssl_context = ssl_context

    async def __aenter__(self):
        for port, servers in self.port_to_server.items():
            integrated_server = IntegratedServer(port)

            integrated_ssl_config = IntegrateSSLConfig()
            for server in servers:
                self._composite_ssl_config(integrated_server, integrated_ssl_config, server)

            self.integrated_servers.append(integrated_server)

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        for task in self.tasks:
            task.cancel()
