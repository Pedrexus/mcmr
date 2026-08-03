from typing import TYPE_CHECKING

from patos import FrozenModel

from .prepared import PreparedRule

if TYPE_CHECKING:
    from ...facts.foundation import Fact


class RuleBatch(FrozenModel):
    """Group rules whose table dependencies form one connected execution graph."""

    rules: list[PreparedRule]

    @property
    def families(self) -> set[type[Fact]]:
        """Return every table needed anywhere in this connected graph."""
        return {family for rule in self.rules for family in rule.families}

    def connected(self, rule: PreparedRule) -> bool:
        """Whether one rule shares a table with this graph."""
        return not self.families.isdisjoint(rule.families)
