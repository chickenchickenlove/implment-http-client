from typing import Literal
from http_2.public.expect_continue_exception import ExpectationFailedException
from abc import ABC, abstractmethod


class Continue100Chains:

    def __init__(self):
        self._chains = []

    def add(self, clazz):
        self._chains.append(clazz())

    def execute(self,
                method: str,
                uri: str,
                protocol: Literal['HTTP/1.1', 'HTTP/1', 'HTTP/2'],
                headers: dict[str, str]):

        for chain in self._chains:
            chain(method, uri, protocol, headers)


CONTINUE_CHAINS = Continue100Chains()


class Continue100Chain(ABC):

    @abstractmethod
    def __call__(self,
                 method: str,
                 uri: str,
                 protocol: Literal['HTTP/1.1', 'HTTP/1', 'HTTP/2'],
                 headers: dict[str, str]) -> None:
        pass


@CONTINUE_CHAINS.add
class CheckExpectationFailedChain(Continue100Chain):

    def __call__(self,
                 method: str,
                 uri: str,
                 protocol: str,
                 headers: dict[str, str]) -> None:
        if 'expect' in headers.keys() and headers['expect'].lower() != '100-continue':
            raise ExpectationFailedException(f'Expect header has unexpected value {headers["expect"]}')
