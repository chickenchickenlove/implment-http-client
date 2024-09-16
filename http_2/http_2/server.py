import asyncio

from asyncio.streams import StreamReader, StreamWriter
from typing import Callable
from data_structure import Trie
from protocol_verifier import ProtocolVerifier

from http1_connection import Http1Connection
from http2_connection import Http2Connection
from generic_http_object import GenericHttpRequest, GenericHttpResponse
from status_code import StatusCode
from ssl_object import SSLConfig


class HttpServerDispatcher:

    URL_CONTEXT = {
        'GET': Trie(),
        'POST': Trie(),
        'DELETE': Trie(),
        'PUT': Trie(),
        'HEAD': Trie(),
    }

    @property
    def url_context(self):
        return HttpServerDispatcher.URL_CONTEXT

    @staticmethod
    def route(path: str, methods: list[str]) -> Callable:
        def decorator(func):
            for method in methods:
                HttpServerDispatcher.URL_CONTEXT.get(method).add(path, func)
            return func
        return decorator

    @staticmethod
    def request_mapping(path: str) -> Callable:
        return HttpServerDispatcher.route(path, ['GET', 'POST', 'DELETE', 'PUT', 'HEAD'])

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

    @staticmethod
    async def graceful_shutdown(timeout: int):
        # TODO : NEED TO BE
        # await asyncio.sleep(timeout)
        # for task in asyncio.all_tasks():
        #     task.cancel()
        #     task.done()
        pass

    async def dispatch(self, http_request: GenericHttpRequest, http_response: GenericHttpResponse):

        path = http_request.path
        func = self.url_context.get(http_request.method).search(path)

        if not func:
            http_response.status_code = StatusCode.NOT_FOUND
            return http_request, http_response
        else:
            response = await func(http_request, http_response)
            return http_request, response

    async def __call__(self, client_reader: StreamReader, client_writer: StreamWriter):
        try:
            # client_writer.start_tls()
            protocol, first_line = await ProtocolVerifier.ensure_protocol(client_reader)
            match protocol:
                case 'HTTP/2':
                    connection = await Http2Connection.create(client_reader, client_writer, self.dispatch)
                    try:
                        async with asyncio.TaskGroup() as tg:
                            tg.create_task(connection.parse_http2_frame())
                            tg.create_task(connection.consume_complete_stream())
                    except Exception as e:
                        print(f'Unexpected Exception occurs. error : {e}')
                    pass
                case 'HTTP/1':
                    await Http1Connection(client_reader, client_writer, first_line).handle_request(self.dispatch)
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


class Server:

    def __init__(self, host: str, port: int, /, ssl_config: SSLConfig):
        self.host = host
        self.port = port
        self.ssl_config = ssl_config if ssl_config else None

    async def serve_forever(self):

        if self.ssl_config:
            ssl_context = self.ssl_config.default_ssl_context
            ssl_context.set_servername_callback(self.ssl_config.sni_callback)
            http_server = await asyncio.start_server(HttpServerDispatcher(), self.host, self.port, ssl=ssl_context)
        else:
            http_server = await asyncio.start_server(HttpServerDispatcher(), self.host, self.port)
        async with http_server:
            await asyncio.gather(http_server.serve_forever())
