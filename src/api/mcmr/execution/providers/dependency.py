from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from patos import FrozenModel
from pydantic import JsonValue

from ...facts import DependencyFact, Fact
from ...project.dependencies import DependencyRefresher, UrlJsonTransport
from ...table import RepositoryTables, fact_table

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence


class DependencyProvider(FrozenModel):
    """Collect current dependency registry evidence for one repository."""

    families: ClassVar[set[type[Fact]]] = {DependencyFact}
    repository: Path
    settings: Mapping[str, JsonValue] = {}
    workers: int = 8
    timeout_seconds: int = 30

    async def collect(self) -> Sequence[Fact]:
        """Return current dependency evidence without retaining an artifact."""
        refresher = DependencyRefresher(
            root=self.repository,
            workers=self.workers,
            transport=UrlJsonTransport(timeout_seconds=self.timeout_seconds),
        )
        return [await refresher.refresh()]

    async def tables(self, families: Collection[type[Fact]]) -> RepositoryTables:
        """Build the dependency table only when this provider owns the request."""
        tables = RepositoryTables()
        if DependencyFact in families:
            tables.add(fact_table(DependencyFact, await self.collect()))
        return tables
