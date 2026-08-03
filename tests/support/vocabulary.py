import ast
import re
from collections.abc import MutableMapping
from functools import cache
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

from patos import FrozenModel

from .fixtures import built_catalog, family_of

if TYPE_CHECKING:
    from mcmr.facts import Fact

_MATCHED = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:/-]*$")
_NEUTRAL = ["", "src/orders.py", "tests/test_orders.py", "shop/api.py", "self", "total", "value"]
_READERS = {"of_kind": "kind", "names": "kind", "startswith": "", "endswith": ""}


class Vocabulary(FrozenModel):
    """Collect the closed words rules compare against each fact field."""

    found: MutableMapping[str, set[str]]

    def call(self, node: ast.Call) -> None:
        """Keep arguments passed into one recognized fact-field reader."""
        for item in node.args:
            self.keep(item, self.read(node.func))

    def comparison(self, node: ast.Compare) -> None:
        """Keep every literal compared against the field either side names."""
        operands = [node.left, *node.comparators]
        name = next((name for item in operands if (name := self.read(item))), "")
        for item in operands:
            self.keep(item, name)

    def keep(self, node: ast.expr, name: str) -> None:
        """Keep string literals carried by one decision operand."""
        match node:
            case ast.Constant(value=str() as word) if _MATCHED.match(word):
                self.found.setdefault(name, set()).add(word)
                self.found.setdefault("", set()).add(word)
            case ast.Set(elts=elements) | ast.Tuple(elts=elements) | ast.List(elts=elements):
                for element in elements:
                    self.keep(element, name)
            case _:
                return

    def read(self, node: ast.expr) -> str:
        """Return the field name one comparison operand represents, when it names one."""
        match node:
            case ast.Attribute(attr=attribute):
                return attribute
            case ast.Call(func=ast.Attribute(value=receiver, attr=method)) if method in _READERS:
                return _READERS[method] or self.read(receiver)
            case _:
                return ""

    def record(self, source: str) -> None:
        """Record the words one rule module decides on, grouped by compared field."""
        for node in ast.walk(ast.parse(source)):
            match node:
                case ast.Compare():
                    self.comparison(node)
                case ast.Call(func=ast.Attribute(attr=method)) if method in _READERS:
                    self.call(node)
                case ast.Set() | ast.Tuple() | ast.List():
                    self.keep(node, "")
                case _:
                    continue


@cache
def vocabulary(family: type[Fact]) -> dict[str, list[str]]:
    """Return the words rules for one family compare against each fact field."""
    found: dict[str, set[str]] = {"": set(_NEUTRAL)}
    for rule in built_catalog().rules:
        if family_of(rule) is family:
            source = Path(import_module(rule.module).__file__ or "").read_text()
            Vocabulary(found=found).record(source)
    return {name: sorted(words | {""}) for name, words in found.items()}


def neutral_words() -> list[str]:
    """Return the shared neutral words that exercise equality between unrelated fields."""
    return list(_NEUTRAL)
