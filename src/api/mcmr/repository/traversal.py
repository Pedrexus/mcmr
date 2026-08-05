from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from patos import FrozenModel

if TYPE_CHECKING:
    from collections.abc import MutableSequence


class Traversal(FrozenModel):
    """Walk one directed graph while retaining Tarjan's mutable traversal state."""

    adjacency: Mapping[str, Sequence[str]]
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    path: list[str] = []
    active: set[str] = set()
    found: list[list[str]] = []

    def complete(self, node: str, pending: Sequence[tuple[str, int]]) -> None:
        """Complete one explored node and propagate its lowlink to its parent."""
        if self.lowlinks[node] == self.indices[node]:
            self.found.append(self.settle(node))
        if pending:
            holder = pending[-1][0]
            self.lowlinks[holder] = min(self.lowlinks[holder], self.lowlinks[node])

    def components(self) -> list[list[str]]:
        """Walk every disconnected region and return the completed components."""
        for start in sorted(self.adjacency):
            if start not in self.indices:
                self.walk(start)
        return self.found

    def descend(self, node: str, step: int, pending: MutableSequence[tuple[str, int]]) -> bool:
        """Schedule the first unseen neighbor or finish known neighbor updates."""
        for reached in range(step, len(self.adjacency[node])):
            target = self.adjacency[node][reached]
            if target not in self.indices:
                pending.extend(((node, reached + 1), (target, 0)))
                return True
            if target in self.active:
                self.lowlinks[node] = min(self.lowlinks[node], self.indices[target])
        return False

    def enter(self, node: str) -> None:
        """Record a node when the traversal first reaches it."""
        self.indices[node] = self.lowlinks[node] = len(self.indices)
        self.path.append(node)
        self.active.add(node)

    def settle(self, node: str) -> list[str]:
        """Take the nodes above one root off the walk as its completed component."""
        component: list[str] = []
        while True:
            member = self.path.pop()
            self.active.remove(member)
            component.append(member)
            if member == node:
                return component

    def walk(self, start: str) -> None:
        """Complete an iterative depth-first walk from one unseen node."""
        pending: list[tuple[str, int]] = [(start, 0)]
        while pending:
            node, step = pending.pop()
            if step == 0:
                self.enter(node)
            if self.descend(node, step, pending):
                continue
            self.complete(node, pending)
