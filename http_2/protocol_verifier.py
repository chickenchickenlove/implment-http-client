import asyncio
from asyncio.streams import StreamReader, StreamWriter
from typing import Tuple

from http_2.exception import UnknownProtocolException, ClientDoNotSendAnyMessageException


class ProtocolVerifier:

    @classmethod
    async def ensure_protocol(cls, reader: StreamReader) -> Tuple[str, bytes]:
        try:
            coro = reader.readline()
            preface_msg = await asyncio.wait_for(coro, timeout=5)
            if preface_msg == b'PRI * HTTP/2.0\r\n':
                if await cls.confirm_http2_protocol(reader, preface_msg):
                    return 'HTTP/2', preface_msg
            elif ProtocolVerifier.maybe_http1_protocol(preface_msg):
                # TODO
                protocol, is_match = cls.confirm_http1_protocol(preface_msg)
                return protocol, preface_msg
        except asyncio.TimeoutError:
            raise ClientDoNotSendAnyMessageException('Server waited to get Preface msg, but never got any msg from client.')
        raise UnknownProtocolException()

    @classmethod
    def maybe_http1_protocol(cls, preface_msg: bytes):
        return preface_msg.startswith((b'GET', b'POST', b'HEAD', b'PUT', b'DELETE', b'UPDATE'))

    @classmethod
    def confirm_http1_protocol(cls, first_line: bytes):
        def strip_useless_enter(x: str):
            return x.rstrip('\r\n')
        try:
            http_method, uri, protocol = map(strip_useless_enter, first_line.decode().split(' '))
        except Exception:
            raise UnknownProtocolException()

        if http_method not in ['GET', 'POST', 'HEAD', 'PUT', 'DELETE', 'UPDATE']:
            return 'UNKNOWN_PROTOCOL', False

        if not uri.startswith('/'):
            return 'UNKNOWN_PROTOCOL', False

        if not protocol.startswith('HTTP/1'):
            return False

        if not first_line.endswith(b'\r\n'):
            return 'UNKNOWN_PROTOCOL', False

        return protocol, True

    @classmethod
    async def confirm_http2_protocol(cls, reader: StreamReader, preface_msg: bytes) -> bool:
        if preface_msg != b'PRI * HTTP/2.0\r\n':
            return False
        if await reader.readline() != b'\r\n':
            return False
        if await reader.readline() != b'SM\r\n':
            return False
        if await reader.readline() != b'\r\n':
            return False
        return True
