from types import SimpleNamespace
from typing import TYPE_CHECKING

from mcmr.facts import SourceSpan
from mcmr.plugins import RepositoryTables, fact_table

from .fact import PluginFact

if TYPE_CHECKING:
    from mcmr.plugins import Fact, ProviderContext


class PluginProvider:
    """Build one custom family through the public provider protocol."""

    families: dict[type[Fact], set[type[Fact]]] = {PluginFact: set()}

    async def tables(self, context: ProviderContext) -> RepositoryTables:
        assert context.requested == {PluginFact}
        supplied = RepositoryTables()
        supplied.add(
            fact_table(
                PluginFact,
                [
                    PluginFact(
                        key="plugin",
                        span=SourceSpan(path="datahub"),
                        value=str(context.settings["catalog"]),
                    )
                ],
            )
        )
        return supplied


def invalid_plugin_provider() -> SimpleNamespace:
    """Build an object that deliberately omits the provider protocol."""
    return SimpleNamespace()
