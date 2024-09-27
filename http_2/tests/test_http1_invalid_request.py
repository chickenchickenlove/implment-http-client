import asyncio
import pytest
import socket

from http_2.public.response import HttpResponse
from http_2.public.request import HttpRequest
from http_2.status_code import StatusCode
from http_2.server import Server, AsyncServerExecutor

RESPONSE_DATA = 'HELLO'


@pytest.fixture
def server_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


@pytest.fixture
async def server(server_port):
    http_localhost_server = Server(server_port)

    @http_localhost_server.route(path='/hello', methods=['GET'])
    async def return_ok(http_request: HttpRequest, http_response: HttpResponse):
        return HttpResponse(status_code=StatusCode.OK, body=RESPONSE_DATA)

    @http_localhost_server.route(path='/hello-post', methods=['POST'])
    async def return_ok(http_request: HttpRequest, http_response: HttpResponse):
        return HttpResponse(status_code=StatusCode.OK, body='POST!')

    executor = AsyncServerExecutor()
    executor.add_server(http_localhost_server)

    await executor.__aenter__()
    t = asyncio.create_task(executor.execute_forever())
    await asyncio.sleep(1)
    yield t

    await executor.__aexit__('', '', '')
    try:
        t.cancel()
        await t
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_server_should_close_connection_when_client_dont_send_preface_msg(server_port, server):
    # Given
    reader, writer = await asyncio.open_connection(host='localhost', port=server_port)

    # When
    await asyncio.sleep(6)

    # Then
    r = await reader.read(1)
    assert r == b''

@pytest.mark.asyncio
async def test_server_should_close_connection_when_client_send_unknown_preface_msg1(server_port, server):
    # Given
    reader, writer = await asyncio.open_connection(host='localhost', port=server_port)

    # When
    writer.write(b'EVIL PREFACE')
    await writer.drain()

    # Then
    r = await reader.read(1)
    assert r == b''


@pytest.mark.asyncio
async def test_server_should_close_connection_when_client_send_unknown_preface_msg2(server_port, server):
    # Given
    reader, writer = await asyncio.open_connection(host='localhost', port=server_port)

    # When
    writer.write(b'EVIL PREFACE\r\n')
    await writer.drain()

    # Then
    r = await reader.read(1)
    assert r == b''


@pytest.mark.asyncio
async def test_server_should_408_response_when_client_dont_send_header(server_port, server):
    # Given
    reader, writer = await asyncio.open_connection(host='localhost', port=server_port)

    # When
    writer.write(b'GET /hello HTTP/1.1\r\n')
    await writer.drain()

    # Then
    r = await reader.readline()
    assert r == b'HTTP/1.1 408 Request Timeout\r\n'


@pytest.mark.asyncio
async def test_server_should_408_response_when_client_send_invalid_header1(server_port, server):
    # Given
    reader, writer = await asyncio.open_connection(host='localhost', port=server_port)

    # When
    writer.write(b'GET /hello HTTP/1.1\r\n')
    writer.write(b'connection: keep-alive')
    await writer.drain()

    # Then
    r = await reader.readline()
    assert r == b'HTTP/1.1 408 Request Timeout\r\n'


@pytest.mark.asyncio
async def test_server_should_408_response_when_client_send_invalid_header2(server_port, server):
    # Given
    reader, writer = await asyncio.open_connection(host='localhost', port=server_port)

    # When
    writer.write(b'GET /hello HTTP/1.1\r\n')
    writer.write(b'connection: keep-alive\r\n')
    await writer.drain()

    # Then
    r = await reader.readline()
    assert r == b'HTTP/1.1 408 Request Timeout\r\n'


@pytest.mark.asyncio
async def test_server_should_200_response_when_client_send_proper_request(server_port, server):
    # Given
    reader, writer = await asyncio.open_connection(host='localhost', port=server_port)

    # When
    writer.write(b'GET /hello HTTP/1.1\r\n')
    writer.write(b'connection: keep-alive\r\n')
    writer.write(b'\r\n')
    await writer.drain()

    # Then
    r = await reader.readline()
    assert r == b'HTTP/1.1 200 OK\r\n'


@pytest.mark.asyncio
async def test_server_should_408_response_when_client_send_insufficient_body(server_port, server):
    # Given
    reader, writer = await asyncio.open_connection(host='localhost', port=server_port)

    # When
    writer.write(b'POST /hello-post HTTP/1.1\r\n')
    writer.write(b'connection: keep-alive\r\n')
    writer.write(b'content-length: 10\r\n')
    writer.write(b'\r\n')
    await writer.drain()

    # Then
    r = await reader.readline()
    # r = await reader.read(1)
    assert r == b'HTTP/1.1 408 Request Timeout\r\n'


@pytest.mark.asyncio
async def test_server_should_200_response_when_client_send_sufficient_body(server_port, server):
    # Given
    reader, writer = await asyncio.open_connection(host='localhost', port=server_port)

    # When
    writer.write(b'POST /hello-post HTTP/1.1\r\n')
    writer.write(b'connection: keep-alive\r\n')
    writer.write(b'content-length: 3\r\n')
    writer.write(b'\r\n')
    writer.write(b'123\r\n')
    await writer.drain()

    # Then
    r = await reader.readline()
    # r = await reader.read(1)
    assert r == b'HTTP/1.1 200 OK\r\n'

@pytest.mark.asyncio
async def test_server_should_400_response_when_client_send_invalid_content_length_and_body(server_port, server):
    # Given
    reader, writer = await asyncio.open_connection(host='localhost', port=server_port)

    # When
    writer.write(b'POST /hello-post HTTP/1.1\r\n')
    writer.write(b'connection: keep-alive\r\n')
    writer.write(b'content-length: 10\r\n')
    writer.write(b'\r\n')
    writer.write(b'123\r\n')
    await writer.drain()

    # Then
    r = await reader.readline()
    # r = await reader.read(1)
    assert r == b'HTTP/1.1 400 Bad Request\r\n'
