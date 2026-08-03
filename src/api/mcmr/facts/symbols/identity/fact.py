from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from ..typing.scope import TypingScope
    from .symbol import Symbol


class SymbolFact(Fact):
    """Describe one resolved symbol declaration and its uses."""

    symbols: list[Symbol] = []
    typing_scopes: list[TypingScope] = []
