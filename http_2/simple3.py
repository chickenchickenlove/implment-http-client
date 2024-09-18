import asyncio

from hyperframe.frame import GoAwayFrame
from protocol_verifier import verify_protocol
from asyncio.streams import StreamReader, StreamWriter
from http2_connection import Http2Connection


def useless_func():
    print('called useless func.')

async def execute(client_reader: StreamReader, client_writer: StreamWriter):

    connection = await Http2Connection.create(client_reader, client_writer, useless_func)
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(connection.parse_http2_frame())
            tg.create_task(connection.consume_complete_stream())
    except Exception as e:
        print(f'hehe : {e}')


async def handle_request(client_reader: StreamReader, client_writer: StreamWriter):
    try:
        is_valid_http2 = await verify_protocol(client_reader)
        if is_valid_http2:
            await execute(client_reader, client_writer)
        else:
            # https://datatracker.ietf.org/doc/html/rfc9113#name-error-codes
            frame = GoAwayFrame(error_code=1)
            client_writer.write(frame.serialize())
            await client_writer.drain()
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


async def main():
    http_server = await asyncio.start_server(handle_request, '127.0.0.1', 8080)
    async with http_server:
        await asyncio.gather(http_server.serve_forever())


if __name__ == '__main__':
    asyncio.run(main())


# 헤더 -> Continuation -> DATA 형태로 와야함.
# 헤더 -> DATA -> 헤더 형식으로 오려면 trailering 형태여야 함.
