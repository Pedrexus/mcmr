from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ....facts import Fact
    from ....table import RepositoryTables
    from .context import ProviderContext


@runtime_checkable
class FactProvider(Protocol):
    """Build the external fact families one installed plugin owns."""

    families: ClassVar[dict[type[Fact], set[type[Fact]]]]

    async def tables(self, context: ProviderContext) -> RepositoryTables: ...
