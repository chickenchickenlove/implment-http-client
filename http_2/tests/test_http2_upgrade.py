import asyncio
import pytest
import socket

from hyperframe.frame import SettingsFrame, HeadersFrame
from collections import deque

from http_2.exception import NeedToChangeProtocolException
from http_2.common_http_object import GenericHttpRequest, GenericHttpResponse
from http_2.status_code import StatusCode
from http_2.http1_response import GeneralHttp1Response
from http_2.server import Server, AsyncServerExecutor


RETURN_RESULT = 'HELLO_TEST_HTTP2_UPGRADE'

@pytest.fixture
def server_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


@pytest.fixture
async def server(server_port):
    http_localhost_server = Server(server_port)

    @http_localhost_server.route(path='/hello/ballo2', methods=['POST', 'GET'])
    async def return_ok(http_request: GenericHttpRequest, http_response: GenericHttpResponse):
        return GeneralHttp1Response(status_code=StatusCode.OK, body=RETURN_RESULT)

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


def test_should_have_expected_frames():
    # Given
    http2_settings = 'AAMAAABkAAQAoAAAAAIAAAAA'
    headers = {
        'Host': 'localhost:8080',
        'User-Agent': 'curl/8.9.1',
        'Accept': '*/*',
        'Connection': 'Upgrade, HTTP2-Settings',
        'Upgrade': 'h2c',
        'HTTP2-Settings': http2_settings
    }

    protocol_exception = NeedToChangeProtocolException(
        method='GET',
        path='/hello/ballo',
        headers=headers,
        http2_settings_headers=http2_settings,
        response_msg=b'HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\nUpgrade: h2c\r\n\r\n'
    )
    expected_frames_type = [SettingsFrame, HeadersFrame]

    # When
    result_frames = deque([])
    while protocol_exception.has_next_frame():
        result_frames.append(protocol_exception.next_frame)

    # Then
    for frame, expected_type in zip(result_frames, expected_frames_type):
        assert isinstance(frame, expected_type) is True


@pytest.mark.asyncio
async def test_should_upgrade_protocol_with_no_body(server_port, server):

    # Given
    cmds = ['curl', '--http2', f'http://localhost:{server_port}/hello/ballo2', '-vvv']
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
    assert 'HTTP/1.1 101 Switching Protocols' in stderr.decode()
    assert 'Connection: Upgrade' in stderr.decode()
    assert 'Upgrade: h2c' in stderr.decode()
    assert 'HTTP/2 200' in stderr.decode()


@pytest.mark.asyncio
async def test_should_ignore_upgrade_protocol_with_body(server_port, server):

    # Given
    cmds = ['curl',
            f'http://localhost:{server_port}/hello/ballo2',
            '-vvv',
            '--http2',
            '-H "Content-Type: plain/text"',
            '-d "HI."'
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
    assert 'HTTP/1.1 101 Switching Protocols' not in stderr.decode()
    assert 'HTTP/1.1 200 OK' in stderr.decode()
