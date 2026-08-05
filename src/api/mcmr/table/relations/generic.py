from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import polars as pl

    from ...facts.foundation import Fact
    from ..runtime.table import Table


class FactRelations[Family: Fact]:
    """Query one schema-normalized fact family through its universal relations."""

    def __init__(self, table: Table[Family]) -> None:
        self.table = table

    def counted(self, selected: pl.LazyFrame, value: pl.Expr | None = None) -> pl.LazyFrame:
        """Attach one selected-row count or sum to every fact."""
        return self.table.counted(selected, value)

    def coverage(self, population: pl.LazyFrame, complete: pl.Expr) -> pl.LazyFrame:
        """Attach the percentage of selected raw records satisfying one rule-owned predicate."""
        return self.table.coverage(population, complete)

    def facts(self) -> pl.LazyFrame:
        """Return fact rows with their ordered provider evidence."""
        return self.table.facts()

    def records(self, relation: str) -> pl.LazyFrame:
        """Return object records from one exact schema relation."""
        return self.table.records(relation)

    def value_counts(self, relation: str) -> pl.LazyFrame:
        """Attach the number of scalar values in one relation to every fact."""
        return self.table.value_counts(relation)

    def values(self, relation: str) -> pl.LazyFrame:
        """Return scalar values from one exact schema relation."""
        return self.table.values(relation)
