from typing import TYPE_CHECKING

from patos import FrozenModel

from ..domain.contracts import RuleScope

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .catalog import RuleDefinition


class LanguageScope(FrozenModel):
    """Keep only the rules an analyzed repository holds a language for."""

    observed: set[str] = set()

    def holds(self, definition: RuleDefinition) -> bool:
        """Whether one rule is general or answers for a language this repository was seen in."""
        if not self.observed or definition.scope is RuleScope.GENERAL:
            return True
        return str(definition.scope) in self.observed

    def selected(self, definitions: Sequence[RuleDefinition]) -> list[RuleDefinition]:
        """Return the definitions this repository has any source to answer for."""
        return [definition for definition in definitions if self.holds(definition)]
