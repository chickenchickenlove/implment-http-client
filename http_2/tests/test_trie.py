import pytest
from typing import Callable

from http_2.data_structure import Trie

def test_trie1():
    # When
    trie = Trie()

    # Then
    assert trie.node is not None



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
def test_trie2(path: str,
              func: Callable,
              expected_func: Callable):

    # Given
    trie = Trie()
    # path = '/a/b/c'

    # When
    trie.add(path, func)

    # Then
    result = trie.search(path)
    assert result == expected_func


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
    assert trie.search(path1) == f1
    assert trie.search(path2) == f2
    assert trie.search(path3) == f3
    assert trie.search(path4) == f4
