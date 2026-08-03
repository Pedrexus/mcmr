from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Collection

    from ...facts import Fact
    from ...table import RepositoryTables


@runtime_checkable
class FactProvider(Protocol):
    """Build the external fact families one installed plugin owns."""

    families: ClassVar[set[type[Fact]]]

    async def tables(self, families: Collection[type[Fact]]) -> RepositoryTables: ...
