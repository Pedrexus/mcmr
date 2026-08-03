import polars as pl
from patos import FrozenModel, Runtime

from ...facts import SyntaxFact
from ..models import Table
from ..names import SyntaxRelation


class SyntaxTable(FrozenModel):
    """Expose raw syntax relations and derive node text only inside lazy queries."""

    table: Runtime[Table[SyntaxFact]]

    @property
    def children(self) -> pl.LazyFrame:
        """Return stable direct child edges between compact node ordinals."""
        return self.table.lazy(SyntaxRelation.CHILDREN)

    @property
    def facts(self) -> pl.LazyFrame:
        """Return declaration rows carrying each retained source exactly once."""
        return self.table.lazy(SyntaxRelation.FACTS)

    @property
    def nodes(self) -> pl.LazyFrame:
        """Return compact node rows without materializing their source slices."""
        return self.table.lazy(SyntaxRelation.NODES)

    def with_text(self, nodes: pl.LazyFrame) -> pl.LazyFrame:
        """Slice text only for the already narrowed node relation a query needs."""
        if "text" in nodes.collect_schema():
            return nodes
        return (
            nodes.join(self._sources, on="fact_order", how="left", validate="m:1")
            .with_columns(self._text)
            .drop("source")
        )

    @property
    def _sources(self) -> pl.LazyFrame:
        """Return the source column keyed by fact order."""
        return self.facts.select("fact_order", "source")

    @property
    def _text(self) -> pl.Expr:
        """Slice each selected node from its source bytes."""
        return (
            pl.col("source")
            .cast(pl.Binary)
            .bin.slice(pl.col("byte_start"), pl.col("byte_length"))
            .cast(pl.String)
            .alias("text")
        )
