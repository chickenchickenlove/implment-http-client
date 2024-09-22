from asyncio.streams import StreamWriter

from http_2.internal.http1_response import Http1Response, Http1StreamingResponse
from http_2.internal.http1_writer import GeneralHttp1ResponseWriter, ChunkedResponseWriter

from http_2.internal.interface_response import Response


class Http1ResponseWriterSelector:

    @staticmethod
    async def write(response: Response, writer: StreamWriter):
        if isinstance(response, Http1StreamingResponse):
            selected_writer = ChunkedResponseWriter(writer)
            await selected_writer.write(response)
        elif isinstance(response, Http1Response):
            selected_writer = GeneralHttp1ResponseWriter(writer)
            await selected_writer.write(response)
        else:
            raise NotImplemented(f'WriterSelector got unexpected response type {response}')
