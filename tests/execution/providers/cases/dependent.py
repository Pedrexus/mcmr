from typing import TYPE_CHECKING

from mcmr.facts import FunctionFact, SourceSpan
from mcmr.plugins import RepositoryTables, fact_table

from ..fact import PluginFact

if TYPE_CHECKING:
    from mcmr.plugins import ProviderContext


class DependentPluginProvider:
    """Build plugin evidence from a declared native function table."""

    families = {PluginFact: {FunctionFact}}

    async def tables(self, context: ProviderContext) -> RepositoryTables:
        """Expose the number of native functions received through injection."""
        count = context.table(FunctionFact).facts().collect().height
        tables = RepositoryTables()
        tables.add(
            fact_table(
                PluginFact,
                [
                    PluginFact(
                        key="plugin",
                        span=SourceSpan(path="provider"),
                        value=str(count),
                    )
                ],
            )
        )
        return tables
