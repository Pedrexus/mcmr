from collections.abc import Mapping
from functools import cached_property
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING, cast

from patos import FrozenModel
from pydantic import JsonValue

from ...table import RepositoryTables
from .contracts import FactProvider, ProviderContext, ProviderExecutionError, ResultPublisher

if TYPE_CHECKING:
    from collections.abc import Collection

    from ...facts.foundation import Fact


class ExternalEvidence(FrozenModel):
    """Resolve enabled network facts through explicit in-memory providers."""

    repository: Path
    settings: Mapping[str, Mapping[str, JsonValue]] = {}
    plugin_group: str = "mcmr.providers"

    @cached_property
    def owners(self) -> dict[type[Fact], str]:
        """Return the unique provider that owns every installed external family."""
        owners: dict[type[Fact], str] = {}
        for name, provider in self.providers.items():
            for family in provider.families:
                if previous := owners.get(family):
                    raise ValueError(
                        f"fact family {family.__name__} is owned by providers "
                        f"{previous} and {name}"
                    )
                owners[family] = name
        return owners

    @property
    def provided(self) -> set[type[Fact]]:
        """Return every fact family an installed provider can build."""
        return set(self.owners)

    @cached_property
    def providers(self) -> dict[str, FactProvider]:
        """Load built-in and installed providers in stable entry-point order."""
        loaded = {
            entry.name: entry.load()
            for entry in sorted(
                metadata.entry_points(group=self.plugin_group),
                key=lambda item: (item.name, item.value),
            )
        }
        providers: dict[str, FactProvider] = {}
        for name, factory in loaded.items():
            if not callable(factory):
                raise TypeError(f"MCMR fact provider {name} must load a callable factory")
            provider = factory()
            if not isinstance(provider, FactProvider):
                raise TypeError(f"MCMR fact provider {name} does not implement FactProvider")
            providers[name] = provider
        return providers

    @property
    def publishers(self) -> dict[str, ResultPublisher]:
        """Return only the installed providers that can write one run back to their system."""
        return {
            name: provider
            for name, provider in self.providers.items()
            if isinstance(provider, ResultPublisher)
        }

    @classmethod
    def for_repository(
        cls,
        root: Path,
        settings: Mapping[str, Mapping[str, JsonValue]] | None = None,
    ) -> ExternalEvidence:
        """Retain the repository external providers receive when requested."""
        return cls(repository=Path(root), settings={} if settings is None else settings)

    def requirements(self, families: Collection[type[Fact]]) -> set[type[Fact]]:
        """Return every typed dependency needed to build the requested external families."""
        required: set[type[Fact]] = set()
        for name, requested in self.selection(families).items():
            for family in requested:
                required.update(self.providers[name].families[family])
        return required

    def selection(self, families: Collection[type[Fact]]) -> dict[str, set[type[Fact]]]:
        """Resolve requested families and every provider dependency they transitively need."""
        pending = set(families) & self.provided
        resolved: set[type[Fact]] = set()
        selected: dict[str, set[type[Fact]]] = {}
        while pending:
            family = pending.pop()
            if family in resolved:
                continue
            resolved.add(family)
            owner = self.owners[family]
            selected.setdefault(owner, set()).add(family)
            pending.update(self.providers[owner].families[family] & self.provided)
        return selected

    async def tables(
        self,
        families: Collection[type[Fact]],
        dependencies: RepositoryTables | None = None,
    ) -> RepositoryTables:
        """Collect requested families after their typed provider dependencies are ready."""
        selected = self.selection(families)
        available = RepositoryTables(dependencies)
        supplied_tables = RepositoryTables()
        while selected:
            required = {
                name: {
                    dependency
                    for family in requested
                    for dependency in self.providers[name].families[family]
                }
                for name, requested in selected.items()
            }
            ready = [name for name in selected if required[name] <= set(available)]
            if not ready:
                self._raise_dependency_error(
                    selected,
                    cast("set[type[Fact]]", set(available)),
                )
            for name in ready:
                requested = selected.pop(name)
                provider = self.providers[name]
                context = ProviderContext(
                    repository=self.repository,
                    settings=self.settings.get(name, {}),
                    requested=requested,
                    dependencies=self._dependencies(available, required[name]),
                )
                supplied = await self._read_provider(name, provider, context)
                self._validate_supply(name, requested, supplied)
                for family in supplied:
                    available.add(supplied[family])
                    supplied_tables.add(supplied[family])
        return supplied_tables

    @staticmethod
    def _dependencies(
        available: RepositoryTables,
        required: Collection[type[Fact]],
    ) -> RepositoryTables:
        """Expose only the dependencies one provider declared."""
        return RepositoryTables({family: available[family] for family in required})

    @staticmethod
    async def _read_provider(
        name: str,
        provider: FactProvider,
        context: ProviderContext,
    ) -> RepositoryTables:
        """Read one provider and retain validation failure ownership at this boundary."""
        try:
            return await provider.tables(context)
        except ValueError as error:
            raise ProviderExecutionError(name, error) from None

    @staticmethod
    def _validate_supply(
        name: str,
        requested: set[type[Fact]],
        supplied: RepositoryTables,
    ) -> None:
        """Require one provider to return exactly the families selected from it."""
        if set(supplied) != requested:
            expected = ", ".join(sorted(family.__name__ for family in requested))
            raise RuntimeError(f"MCMR fact provider {name} did not supply exactly {expected}")

    def _raise_dependency_error(
        self,
        selected: Mapping[str, set[type[Fact]]],
        available: Collection[type[Fact]],
    ) -> None:
        """Distinguish unavailable provider inputs from a provider dependency cycle."""
        pending_outputs = {family for families in selected.values() for family in families}
        missing: set[type[Fact]] = set()
        for name, requested in selected.items():
            for output in requested:
                missing.update(
                    family
                    for family in self.providers[name].families[output]
                    if family not in available and family not in pending_outputs
                )
        if missing:
            names = ", ".join(sorted(family.__name__ for family in missing))
            raise RuntimeError(f"MCMR fact providers require unavailable families {names}")
        names = ", ".join(sorted(selected))
        raise RuntimeError(f"MCMR fact provider dependency cycle includes {names}")
