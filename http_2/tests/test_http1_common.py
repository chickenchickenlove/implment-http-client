import asyncio
import pytest
import socket

from http_2.common_http_object import GenericHttpRequest, GenericHttpResponse
from http_2.status_code import StatusCode
from http_2.http1_response import GeneralHttp1Response
from http_2.server import Server, AsyncServerExecutor

RETURN_RESULT = '/HELLO_CALLED!'
RESULT_400 = 'Invalid Request'

@pytest.fixture
def server_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


@pytest.fixture
async def server(server_port):
    http_localhost_server = Server(server_port)

    @http_localhost_server.route(path='/hello', methods=['GET', 'POST'])
    async def return_ok(http_request: GenericHttpRequest, http_response: GenericHttpResponse):
        return GeneralHttp1Response(status_code=StatusCode.OK, body=RETURN_RESULT + http_request.body)

    @http_localhost_server.route(path='/400', methods=['GET', 'POST'])
    async def return_400(http_request: GenericHttpRequest, http_response: GenericHttpResponse):
        return GeneralHttp1Response(status_code=StatusCode.BAD_REQUEST, body=RESULT_400)

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
async def test_should_receive_200_with_get(server_port, server):
    # Given
    cmds = ['curl',
            f'http://localhost:{server_port}/hello',
            '-vvv',
            ]
    expected_response = RETURN_RESULT

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


@pytest.mark.asyncio
async def test_should_receive_200_with_post_and_body(server_port, server):
    # Given
    req_body = 'HI'
    cmds = ['curl',
            f'http://localhost:{server_port}/hello',
            '-vvv',
            '-d', req_body
            ]

    expected_response = RETURN_RESULT + req_body

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

@pytest.mark.asyncio
async def test_should_receive_400_with_get(server_port, server):
    # Given
    req_body = 'HI'
    cmds = ['curl',
            f'http://localhost:{server_port}/400',
            '-vvv',
            ]

    expected_response = RESULT_400

    # When
    process = await asyncio.create_subprocess_exec(
        *cmds,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    # Then
    stdout, stderr = await process.communicate()

    assert stdout.decode() == expected_response
    assert 'HTTP/1.1 400 Bad Request' in stderr.decode()
