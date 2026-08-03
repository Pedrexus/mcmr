import polars as pl

from .....facts import InteropFact
from .....table.relations import FactRelations


class InteropTables(FactRelations[InteropFact]):
    """Expose cross-language references beside their declared artifacts."""

    def crossings(self) -> pl.LazyFrame:
        """Return references that cross out of the declaring language."""
        return self.references().filter(
            (pl.col("language") != pl.col("declared_language"))
            & (pl.col("language") != "manifest")
        )

    def references(self) -> pl.LazyFrame:
        """Return every reference with its artifact identity and provider evidence."""
        artifacts = self.facts().select(
            "fact_id",
            "mechanism",
            "name",
            "declared_language",
            "evidence",
        )
        return self.records("references").join(artifacts, on="fact_id", how="left")
