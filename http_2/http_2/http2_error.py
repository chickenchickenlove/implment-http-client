


class Http2ConnectionError(Exception):


    def __init__(self, msg):
        self.msg = msg
