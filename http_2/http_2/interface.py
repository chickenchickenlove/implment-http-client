from hyperframe.frame import Frame
from typing import Callable
from error_code import StreamErrorCode

class ConnectionInterface:
    def update_window_size(self, frame: Frame):
        raise NotImplementedError()

    def update_setting(self, frame: Frame):
        raise NotImplementedError()

    def cancel_stream(self, stream_id: int):
        raise NotImplementedError()


    async def break_out_frame(self, stream_id: int, error_code: StreamErrorCode):
        raise NotImplementedError()


    def update_stream(self):
        raise NotImplementedError()


    async def completed_partial_stream(self):
        raise NotImplementedError()


    def has_been_done(self):
        raise NotImplementedError()


    def find_stream(self):
        raise NotImplementedError()


    def publish_window_update(self):
        raise NotImplementedError()


    def remove_stream_by_force(self):
        raise NotImplementedError()

class Http2ConnectionInterface(ConnectionInterface):

    def __init__(self, /,
                 update_window_size: Callable = None,
                 update_setting: Callable = None,
                 cancel_stream: Callable = None,
                 break_out_frame: Callable = None,
                 update_stream: Callable = None,
                 completed_partial_stream: Callable = None,
                 has_been_done: Callable = None,
                 find_stream: Callable = None,
                 publish_window_update: Callable = None,
                 remove_stream_by_force: Callable = None):

        self._update_window_size = update_window_size
        self._update_setting = update_setting
        self._cancel_stream = cancel_stream
        self._break_out_frame = break_out_frame
        self._update_stream = update_stream
        self._completed_partial_stream = completed_partial_stream
        self._has_been_done = has_been_done
        self._find_stream = find_stream
        self._publish_window_update = publish_window_update
        self._remove_stream_by_force = remove_stream_by_force

    def update_window_size(self, frame: Frame):
        return self._update_window_size(frame)

    def update_setting(self, frame: Frame):
        return self._update_setting(frame)

    def cancel_stream(self, stream_id: int):
        return self._cancel_stream(stream_id)

    async def break_out_frame(self, stream_id: int, error_code: StreamErrorCode):
        return await self._break_out_frame(stream_id, error_code)

    def update_stream(self):
        return self._update_stream()

    async def completed_partial_stream(self):
        return await self._completed_partial_stream()

    def has_been_done(self):
        return self._has_been_done()

    def find_stream(self):
        return self._find_stream()

    def publish_window_update(self):
        return self._publish_window_update()

    def remove_stream_by_force(self):
        return self._remove_stream_by_force()
