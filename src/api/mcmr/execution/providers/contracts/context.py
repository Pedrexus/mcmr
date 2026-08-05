from collections.abc import Mapping
from pathlib import Path

from patos import FrozenModel, Runtime
from pydantic import JsonValue

from ....facts import Fact
from ....table import RepositoryTables, Table


class ProviderContext(FrozenModel):
    """Give one provider its request, settings, and already extracted dependencies."""

    repository: Path
    settings: Mapping[str, JsonValue] = {}
    requested: set[type[Fact]]
    dependencies: Runtime[RepositoryTables]

    def table[Family: Fact](self, family: type[Family]) -> Table[Family]:
        """Return one dependency the provider declared before execution."""
        if family not in self.dependencies:
            raise KeyError(f"provider did not declare {family.__name__} as a dependency")
        return self.dependencies[family]
