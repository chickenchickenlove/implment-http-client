import inspect

import pytest

from http_2.context import HTTP1RequestContext, HTTP1ConnectionContext
from http_2.resolver import ArgumentResolver
from http_2.http1_connection import Http1Connection, Http1Request


@pytest.fixture
def mock_conn(mocker):
    mock_conn = mocker.Mock(spec=Http1Connection)
    mock_conn.__class__ = Http1Connection
    return mock_conn

@pytest.fixture
def mock_req(mocker):
    mock_req = mocker.Mock()
    mock_req.__clas__ = Http1Request
    return mock_req


def test_argument_resolve1(mock_conn, mock_req):

    # Given
    class ObjectForTest:
        pass

    def f1(hello: str):
        pass

    conn_ctx = HTTP1ConnectionContext(mock_conn)
    req_ctx = HTTP1RequestContext(mock_req)
    req_ctx.add_param('hello', '123')
    req_ctx.add_param('random', ObjectForTest())

    required_args = [name for name in inspect.signature(f1).parameters.keys()]
    annotations = inspect.get_annotations(f1)

    # When
    result = ArgumentResolver.resolve(required_args, annotations, conn_ctx, req_ctx)

    # Then
    assert len(result) == 1
    assert result['hello'] == '123'


def test_argument_resolve2(mock_conn, mock_req):

    # Given
    class ObjectForTest:
        pass

    def f1(hello: str, test_obj: ObjectForTest):
        pass

    test_obj = ObjectForTest()

    conn_ctx = HTTP1ConnectionContext(mock_conn)
    req_ctx = HTTP1RequestContext(mock_req)
    req_ctx.add_param('hello', '123')
    req_ctx.add_param('test_obj', test_obj)

    required_args = [name for name in inspect.signature(f1).parameters.keys()]
    annotations = inspect.get_annotations(f1)

    # When
    result = ArgumentResolver.resolve(required_args, annotations, conn_ctx, req_ctx)

    # Then
    assert len(result) == 2
    assert result['hello'] == '123'
    assert result['test_obj'] == test_obj


def test_argument_resolve3(mock_conn, mock_req):

    # Given
    class ObjectForTest:
        pass

    def f1(hello, test_obj):
        pass

    test_obj = ObjectForTest()

    conn_ctx = HTTP1ConnectionContext(mock_conn)
    req_ctx = HTTP1RequestContext(mock_req)
    req_ctx.add_param('hello', '123')
    req_ctx.add_param('test_obj', test_obj)

    required_args = [name for name in inspect.signature(f1).parameters.keys()]
    annotations = inspect.get_annotations(f1)

    # When
    result = ArgumentResolver.resolve(required_args, annotations, conn_ctx, req_ctx)

    # Then
    assert len(result) == 2
    assert result['hello'] == '123'
    assert result['test_obj'] == test_obj


def test_req_ctx_should_have_priority(mock_conn, mock_req):

    # Given
    class ObjectForTest:
        pass

    def f1(hello: str, test_obj):
        pass

    test_obj = ObjectForTest()

    conn_ctx = HTTP1ConnectionContext(mock_conn)
    conn_ctx.add_param('hello', 456)
    req_ctx = HTTP1RequestContext(mock_req)
    req_ctx.add_param('hello', '123')
    req_ctx.add_param('test_obj', test_obj)

    required_args = [name for name in inspect.signature(f1).parameters.keys()]
    annotations = inspect.get_annotations(f1)

    # When
    result = ArgumentResolver.resolve(required_args, annotations, conn_ctx, req_ctx)

    # Then
    assert len(result) == 2
    assert result['hello'] == '123'
    assert result['test_obj'] == test_obj


def test_conn_ctx_should_have_priority1(mock_conn, mock_req):

    # Given
    class ObjectForTest:
        pass

    def f1(hello: str, test_obj, test_param):
        pass

    test_obj = ObjectForTest()

    conn_ctx = HTTP1ConnectionContext(mock_conn)
    conn_ctx.add_param('hello', 456)
    conn_ctx.add_param('test_param', 789)
    req_ctx = HTTP1RequestContext(mock_req)
    req_ctx.add_param('hello', '123')
    req_ctx.add_param('test_obj', test_obj)

    required_args = [name for name in inspect.signature(f1).parameters.keys()]
    annotations = inspect.get_annotations(f1)

    # When
    result = ArgumentResolver.resolve(required_args, annotations, conn_ctx, req_ctx)

    # Then
    assert len(result) == 3
    assert result['hello'] == '123'
    assert result['test_param'] == 789
    assert result['test_obj'] == test_obj
