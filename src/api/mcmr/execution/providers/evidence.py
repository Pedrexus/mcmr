from collections.abc import Mapping
from functools import cached_property
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING

from patos import FrozenModel
from pydantic import JsonValue

from ...table import RepositoryTables
from .contracts import FactProvider
from .dependency import DependencyProvider

if TYPE_CHECKING:
    from collections.abc import Collection

    from ...facts.foundation import Fact


class ExternalEvidence(FrozenModel):
    """Resolve enabled network facts through explicit in-memory providers."""

    repository: Path
    settings: Mapping[str, Mapping[str, JsonValue]] = {}
    plugin_group: str = "mcmr.providers"

    @cached_property
    def providers(self) -> dict[str, FactProvider]:
        """Load built-in and installed providers in stable entry-point order."""
        loaded = {"dependencies": DependencyProvider}
        loaded.update(
            {
                entry.name: entry.load()
                for entry in sorted(
                    metadata.entry_points(group=self.plugin_group),
                    key=lambda item: (item.name, item.value),
                )
            }
        )
        providers: dict[str, FactProvider] = {}
        for name, factory in loaded.items():
            if not callable(factory):
                raise TypeError(f"MCMR fact provider {name} must load a callable factory")
            provider = factory(repository=self.repository, settings=self.settings.get(name, {}))
            if not isinstance(provider, FactProvider):
                raise TypeError(f"MCMR fact provider {name} does not implement FactProvider")
            providers[name] = provider
        return providers

    @classmethod
    def for_repository(
        cls,
        root: Path,
        settings: Mapping[str, Mapping[str, JsonValue]] | None = None,
    ) -> ExternalEvidence:
        """Retain the repository external providers receive when requested."""
        return cls(repository=Path(root), settings={} if settings is None else settings)

    async def tables(self, families: Collection[type[Fact]]) -> RepositoryTables:
        """Collect only requested families for which a provider exists."""
        requested = set(families)
        owners: dict[type[Fact], str] = {}
        for name, provider in self.providers.items():
            for family in provider.families & requested:
                if previous := owners.get(family):
                    raise ValueError(
                        f"fact family {family.__name__} is owned by providers "
                        f"{previous} and {name}"
                    )
                owners[family] = name
        tables = RepositoryTables()
        for name, provider in self.providers.items():
            owned = {family for family, owner in owners.items() if owner == name}
            if not owned:
                continue
            supplied = await provider.tables(owned)
            if set(supplied) != owned:
                expected = ", ".join(sorted(family.__name__ for family in owned))
                raise RuntimeError(f"MCMR fact provider {name} did not supply exactly {expected}")
            for family in supplied:
                tables.add(supplied[family])
        return tables
