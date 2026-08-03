from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

from ...facts import Fact
from .table import Table

if TYPE_CHECKING:
    from collections.abc import Generator


class RepositoryTables(Mapping[type[Fact], Table[Fact]]):
    """Resolve annotation-declared tables from one repository analysis session."""

    def __init__(self, tables: Mapping[type[Fact], Table[Fact]] | None = None) -> None:
        self.tables = dict(tables or {})

    def __getitem__[Family: Fact](self, family: type[Family]) -> Table[Family]:
        """Return the exact typed table requested by one rule annotation."""
        return cast("Table[Family]", self.tables[family])

    def __iter__(self) -> Generator[type[Fact]]:
        """Yield available table families in insertion order."""
        yield from self.tables

    def __len__(self) -> int:
        """Return how many distinct table families are available."""
        return len(self.tables)

    def add[Family: Fact](self, table: Table[Family]) -> None:
        """Add one exact family once."""
        if table.family in self.tables:
            raise ValueError(f"repository tables repeated {table.family.__name__}")
        self.tables[table.family] = cast("Table[Fact]", table)
