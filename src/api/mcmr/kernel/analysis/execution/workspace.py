from typing import TYPE_CHECKING

from patos import FrozenModel, Runtime

from ....facts import Fact
from ...protocol import KernelStats
from .catalog import requested_facts

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ....domain.contracts import RuleContract


class _WorkspaceModels:
    """Own streamed fact batches and the complete analyzed workspace."""

    class FamilyStream(FrozenModel):
        """Hold one directory-sized family batch while its rules consume it."""

        family: Runtime[type[Fact]]
        facts: Runtime[list[Fact]]

    class Workspace(FrozenModel):
        """Hold the fact streams one kernel run produced, keyed by exact fact type."""

        streams: dict[type[Fact], list[Fact]] = {}
        stats: KernelStats = KernelStats()

        def runnable(self, rules: Sequence[RuleContract]) -> list[RuleContract]:
            """Return rules whose complete table dependency set this workspace holds."""
            return [rule for rule in rules if requested_facts(rule) <= self.streams.keys()]

        def stream[FactType: Fact](self, family: type[FactType]) -> list[FactType]:
            """Return one fact family narrowed to its declared concrete type."""
            return [fact for fact in self.streams.get(family, []) if isinstance(fact, family)]


FamilyStream = _WorkspaceModels.FamilyStream
Workspace = _WorkspaceModels.Workspace
