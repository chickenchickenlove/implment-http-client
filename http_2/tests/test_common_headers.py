import asyncio
import pytest
import socket

from http_2.public.response import HttpResponse
from http_2.public.request import HttpRequest
from http_2.status_code import StatusCode
from http_2.server import Server, AsyncServerExecutor

@pytest.fixture
def server_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

RESPONSE_DATA = 'HELLO'


@pytest.fixture
async def server(server_port):
    http_localhost_server = Server(server_port)

    @http_localhost_server.route(path='/hello', methods=['GET'])
    async def return_ok(http_request: HttpRequest, http_response: HttpResponse):
        return HttpResponse(status_code=StatusCode.OK, body=RESPONSE_DATA)


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
async def test_http1_request_should_have_common_headers_in_their_response(server_port, server):
    # Given
    cmds = ['curl',
            f'http://localhost:{server_port}/hello',
            '-vvv',
            ]
    expected_response = RESPONSE_DATA

    # When
    process = await asyncio.create_subprocess_exec(
        *cmds,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    # Then
    stdout, stderr = await process.communicate()

    assert stdout.decode() == expected_response
    assert 'HTTP/1.1 200 OK' in stderr.decode()

    assert 'server: Ganae-soogongup' in stderr.decode()
    assert 'date: ' in stderr.decode()


@pytest.mark.asyncio
async def test_http2_request_should_have_common_headers_in_their_response(server_port, server):
    # Given
    cmds = ['curl',
            f'http://localhost:{server_port}/hello',
            '--http2-prior-knowledge',
            '-vvv',
            ]
    expected_response = RESPONSE_DATA

    # When
    process = await asyncio.create_subprocess_exec(
        *cmds,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    # Then
    stdout, stderr = await process.communicate()

    assert stdout.decode() == expected_response
    assert 'HTTP/2 200' in stderr.decode()
    assert 'server: Ganae-soogongup' in stderr.decode()
    assert 'date: ' in stderr.decode()
