# import asyncio
# import uuid
# from typing import Union
# from http2_object import Http2Stream
# import uuid
#
#
# class TerminateAwareAsyncioQue:
#
#     TERM_SIGNAL = 'TERMINATE' + uuid.uuid1().hex
#     INIT = 'INIT'
#     CLOSED = 'CLOSED'
#
#     def __init__(self):
#         self.que: asyncio.Queue = asyncio.Queue()
#         self.state = TerminateAwareAsyncioQue.INIT
#
#     def should_terminate(self, data: Union[Http2Stream, str, int]) -> bool:
#         if isinstance(data, str) and data == TerminateAwareAsyncioQue.TERM_SIGNAL:
#             self.state = TerminateAwareAsyncioQue.CLOSED
#         return self.state == TerminateAwareAsyncioQue.CLOSED
#
#     async def send_term_signal(self) -> None:
#         await self.que.put(TerminateAwareAsyncioQue.TERM_SIGNAL)
#
#     async def get(self) -> Http2Stream | str | int:
#         await self.que.get()
#
#     async def put(self, data: Union[Http2Stream, int]) -> None:
#         await self.que.put(data)
#
# class AsyncGenerator:
#
#     TERM_SIGNAL = 'TERMINATE'
#
#     def __init__(self, streams: TerminateAwareAsyncioQue):
#         self.streams = streams
#         self._closing = False
#
#     async def __aiter__(self):
#         while True:
#             data = await self.streams.get()
#             # https://stackoverflow.com/questions/60226557/how-to-forcefully-close-an-async-generator
#             # We cannot close async generator forcely.
#             if self.streams.should_terminate(data):
#                 break
#             yield data
