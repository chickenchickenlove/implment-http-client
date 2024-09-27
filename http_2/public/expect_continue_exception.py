from http_2.status_code import StatusCode
from http_2.exception import NeedResponseToClientRightAwayException


class ExpectationFailedException(NeedResponseToClientRightAwayException):

    def __init__(self, msg: str):
        self._status_code = StatusCode.EXPECTATION_FAILED
        self._response_msg = msg

    @property
    def status_code(self) -> StatusCode:
        return self._status_code

    @property
    def response_msg(self) -> str:
        return self._response_msg


class UnauthorizedException(NeedResponseToClientRightAwayException):

    def __init__(self, msg: str):
        self._status_code = StatusCode.UNAUTHORIZED
        self._response_msg = msg

    @property
    def status_code(self) -> StatusCode:
        return self._status_code

    @property
    def response_msg(self) -> str:
        raise self._response_msg


class ForbiddenException(NeedResponseToClientRightAwayException):

    def __init__(self, msg: str):
        self._status_code = StatusCode.FORBIDDEN
        self._response_msg = msg

    @property
    def status_code(self) -> StatusCode:
        return self._status_code

    @property
    def response_msg(self) -> str:
        raise self._response_msg


class MethodNotAllowedException(NeedResponseToClientRightAwayException):

    def __init__(self, msg: str):
        self._status_code = StatusCode.METHOD_NOT_ALLOWED
        self._response_msg = msg

    @property
    def status_code(self) -> StatusCode:
        return self._status_code

    @property
    def response_msg(self) -> str:
        raise self._response_msg
