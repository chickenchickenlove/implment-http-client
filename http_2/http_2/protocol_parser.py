from asyncio.streams import StreamReader, StreamWriter

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
