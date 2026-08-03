from typing import TYPE_CHECKING

from ....foundation import Fact
from .coupling import ModuleCoupling

if TYPE_CHECKING:
    from pydantic import NonNegativeInt


class ModuleCouplingFact(ModuleCoupling, Fact):
    """Describe one module through Robert Martin's package metrics."""

    declaration_count: NonNegativeInt = 0
    abstract_declaration_count: NonNegativeInt = 0
    dependencies: list[ModuleCoupling] = []

    @property
    def abstractness(self) -> float:
        """Return the share of module types stating a contract."""
        if not self.declaration_count:
            return 0.0
        return self.abstract_declaration_count / self.declaration_count

    @property
    def distance(self) -> float:
        """Return distance from Martin's main sequence."""
        return abs(self.abstractness + self.instability - 1.0)
