from asyncio.streams import StreamReader, StreamWriter


class ProtocolVerifier:

    @classmethod
    async def ensure_protocol(cls, reader: StreamReader) -> str:
        preface_msg = await reader.readline()
        if preface_msg == b'PRI * HTTP/2.0\r\n':
            if await cls.confirm_http2_protocol(reader, preface_msg):
                return 'HTTP/2'
        else:
            # TODO
            http_method, uri, http_version = cls.confirm_http1_protocol(preface_msg)
            return 'HTTP/1'

    @classmethod
    def confirm_http1_protocol(cls, first_line: bytes):
        def strip_useless_enter(x: str):
            return x.rstrip('\r\n')
        http_method, uri, http_version = map(strip_useless_enter, first_line.decode().split(' '))
        return http_method, uri, http_version

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








async def verify_protocol(client_reader: StreamReader):
    # Preface message: b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n'
    if await client_reader.readline() != b'PRI * HTTP/2.0\r\n':
        return False
    if await client_reader.readline() != b'\r\n':
        return False
    if await client_reader.readline() != b'SM\r\n':
        return False
    if await client_reader.readline() != b'\r\n':
        return False
    return True
