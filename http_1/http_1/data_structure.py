from typing import Callable, Self

class Trie:

    def __init__(self):
        self.node: TrieNode = TrieNode()

    def add(self, path, func):
        self.node.add(path, func)

    def search(self, path) -> Callable:
        return self.node.find(path)


class TrieNode:
    children: dict[str, Self]

    def __init__(self):
        self.children = {}
        self._dispatch_func = None

    def find(self, path: str):
        if path == '/':
            return self._dispatch_func
        else:
            first, *remain = path[1:].split('/', 1)
            child_node = self.children.get('/' + first)

            next_path = '/' + remain[0] if remain else '/'
            return child_node.find(next_path)

    # The first node should be starts with '/'.
    def add(self, path: str, dispatch_func):
        if path == '/':
            self.dispatch_func = dispatch_func
        else:
            first, *remain = path[1:].split('/', 1)
            child_node = self.children.get('/' + first, TrieNode())
            self.children['/' + first] = child_node

            next_path = '/' + remain[0] if remain else '/'
            child_node.add(next_path, dispatch_func)

    @property
    def dispatch_func(self):
        return self._dispatch_func

    @dispatch_func.setter
    def dispatch_func(self, dispatch_func: Callable):
        self._dispatch_func = dispatch_func
