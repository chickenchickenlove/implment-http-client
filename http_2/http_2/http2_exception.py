from hyperframe.frame import Frame

class HeaderValidateException(Exception):

    def __init__(self, response_frame: Frame, msg: str):
        self.response_frame = response_frame
        self.msg = msg

class SettingsValueException(Exception):

    def __init__(self, response_frame: Frame):
        self.response_frame = response_frame
