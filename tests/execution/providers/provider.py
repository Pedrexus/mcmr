from types import SimpleNamespace
from typing import TYPE_CHECKING

from mcmr.facts import SourceSpan
from mcmr.table import RepositoryTables, fact_table

from .fact import PluginFact

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping
    from pathlib import Path

    from pydantic import JsonValue

    from mcmr.facts import Fact


class PluginProvider:
    """Build one custom family through the public provider protocol."""

    families = {PluginFact}

    def __init__(
        self,
        *,
        repository: Path,
        settings: Mapping[str, JsonValue],
        empty: bool = False,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.empty = empty

    async def tables(self, families: Collection[type[Fact]]) -> RepositoryTables:
        assert families == {PluginFact}
        supplied = RepositoryTables()
        if not self.empty:
            supplied.add(
                fact_table(
                    PluginFact,
                    [
                        PluginFact(
                            key="plugin",
                            span=SourceSpan(path="datahub"),
                            value=str(self.settings["catalog"]),
                        )
                    ],
                )
            )
        return supplied


def empty_plugin_provider(
    *,
    repository: Path,
    settings: Mapping[str, JsonValue],
) -> PluginProvider:
    """Build a provider that deliberately violates exact family supply."""
    return PluginProvider(repository=repository, settings=settings, empty=True)


def invalid_plugin_provider(
    *,
    repository: Path,
    settings: Mapping[str, JsonValue],
) -> SimpleNamespace:
    """Build an object that deliberately omits the provider protocol."""
    return SimpleNamespace(repository=repository, settings=settings)
