import asyncio

class GeneratorWrapper:

    TERM_SIGNAL = 'TERMINATE'

    def __init__(self, streams: asyncio.Queue):
        self.streams = streams
        self._closing = False

    async def __aiter__(self):
        while True:
            data = await self.streams.get()
            # https://stackoverflow.com/questions/60226557/how-to-forcefully-close-an-async-generator
            # We cannot close async generator forcely.
            if data == GeneratorWrapper.TERM_SIGNAL:
                break
            yield data
