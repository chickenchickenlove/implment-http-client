from abc import ABC, abstractmethod
from asyncio.streams import StreamWriter
from typing import cast

from http_2.public.response import Response


class AbstractHttp1ResponseWriter(ABC):

    async def write(self, response: Response):
        await self._write_status_line(response)
        await self._write_header_lines(response)
        await self._write_body(response)

    @abstractmethod
    async def _write_status_line(self, response: Response):
        pass

    @abstractmethod
    async def _write_header_lines(self, response: Response):
        pass

    @abstractmethod
    async def _write_body(self, response: Response):
        pass

    def get_extra_info(self, key: str):
        if hasattr(self, '_writer'):
            writer = getattr(self, '_writer')
            writer = cast(StreamWriter, writer)
            return writer.transport.get_extra_info(key)
        return None
