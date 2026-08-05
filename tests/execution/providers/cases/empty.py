from typing import TYPE_CHECKING

from mcmr.plugins import RepositoryTables

from ..fact import PluginFact

if TYPE_CHECKING:
    from mcmr.plugins import Fact, ProviderContext


class EmptyPluginProvider:
    """Deliberately violate the exact provider supply contract."""

    families: dict[type[Fact], set[type[Fact]]] = {PluginFact: set()}

    async def tables(self, context: ProviderContext) -> RepositoryTables:
        """Return no table for the family the provider owns."""
        assert context.requested == {PluginFact}
        return RepositoryTables()
