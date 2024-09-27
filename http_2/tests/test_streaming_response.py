import asyncio
import aiohttp
import pytest
import socket

from http_2.public.request import HttpRequest
from http_2.public.response import HttpResponse, StreamingResponse
from http_2.server import Server, AsyncServerExecutor


@pytest.fixture
def server_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


@pytest.fixture
async def server(server_port):
    http_localhost_server = Server(server_port)

    @http_localhost_server.get_mapping(path='/subscribe')
    async def return_ok(http_request: HttpRequest, http_response: HttpResponse):
        async def gen_contents():
            for i in range(5):
                await asyncio.sleep(0.5)
                yield i
        return StreamingResponse(gen_contents(), media_type='text/event-stream')

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
async def test_should_get_streaming_data_and_headers(server_port, server):

    # Given
    cmds = ['curl',
            '--no-buffer',
            f'http://localhost:{server_port}/subscribe',
            '-vvv',
            ]

    # When
    process = await asyncio.create_subprocess_exec(
        *cmds,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    # Then

    stdout, stderr = await process.communicate()

    assert stdout.decode() == '01234'
    assert 'HTTP/1.1 200 OK' in stderr.decode()
    assert 'text/event-stream' in stderr.decode()
