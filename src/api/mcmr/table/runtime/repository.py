from collections.abc import Mapping
from typing import TYPE_CHECKING, Self, cast

from .table import Table, TableFamily

if TYPE_CHECKING:
    from collections.abc import Generator


class RepositoryTables(Mapping[type[TableFamily], Table[TableFamily]]):
    """Resolve annotation-declared tables from one repository analysis session."""

    def __init__[Family: TableFamily](
        self,
        tables: Mapping[type[Family], Table[Family]] | None = None,
    ) -> None:
        self.tables = cast(
            "dict[type[TableFamily], Table[TableFamily]]",
            dict(tables or {}),
        )

    def __getitem__[Family: TableFamily](self, family: type[Family]) -> Table[Family]:
        """Return the exact typed table requested by one rule annotation."""
        return cast("Table[Family]", self.tables[family])

    def __iter__(self) -> Generator[type[TableFamily]]:
        """Yield available table families in insertion order."""
        yield from self.tables

    def __len__(self) -> int:
        """Return how many distinct table families are available."""
        return len(self.tables)

    def add[Family: TableFamily](self, table: Table[Family]) -> Self:
        """Add one exact family once and return this repository."""
        if table.family in self.tables:
            raise ValueError(f"repository tables repeated {table.family.__name__}")
        self.tables[table.family] = cast("Table[TableFamily]", table)
        return self
