import pytest
from pyassert import *
from http_1.data_structure import Trie
from typing import Callable


def test_trie():
    # When
    trie = Trie()

    # Then
    assert_that(trie.node).is_not_equal_to(None)



def func1():
    pass

def func2():
    pass

def func3():
    pass


@pytest.mark.parametrize("path, func, expected_func",
    [
        ('/', func1, func1),
        ('/a/b/c', func2, func2),
        ('/a/b/c/d', func3, func3),
    ]
)
def test_trie(path: str,
              func: Callable,
              expected_func: Callable):

    # Given
    trie = Trie()
    # path = '/a/b/c'

    # When
    trie.add(path, func)

    # Then
    result = trie.search(path)
    assert_that(result).is_equal_to(expected_func)


def test_trie_multiple():
    # Given
    trie = Trie()


    def f1():
        pass

    def f2():
        pass

    def f3():
        pass

    def f4():
        pass

    path1 = '/'
    path2 = '/a/b/c/'
    path3 = '/b/a/c'
    path4 = '/b/a/c/d'

    # When
    trie.add(path1, f1)
    trie.add(path2, f2)
    trie.add(path3, f3)
    trie.add(path4, f4)

    # Then
    assert_that(trie.search(path1)).is_equal_to(f1)
    assert_that(trie.search(path2)).is_equal_to(f2)
    assert_that(trie.search(path3)).is_equal_to(f3)
    assert_that(trie.search(path4)).is_equal_to(f4)
