import polars as pl

from .....facts import ModuleCouplingFact
from .....table.relations import FactRelations


class CouplingRelations(FactRelations[ModuleCouplingFact]):
    """Derive Martin's module metrics from normalized coupling relations."""

    def dependencies(self) -> pl.LazyFrame:
        """Return each dependency beside the metrics of its importing module."""
        dependency_total = pl.col("afferent_count") + pl.col("efferent_count")
        dependencies = self.records("dependencies").select(
            "fact_order",
            "fact_id",
            "record_id",
            "ordinal",
            pl.col("module").alias("dependency_module"),
            (
                pl.when(dependency_total > 0)
                .then(pl.col("efferent_count") / dependency_total)
                .otherwise(0.0)
                .alias("dependency_instability")
            ),
        )
        modules = self.modules().select(
            "fact_order",
            "fact_id",
            "path",
            "start_line",
            "start_column",
            "end_line",
            "end_column",
            "language",
            "evidence",
            "module",
            "afferent_count",
            "instability",
        )
        return dependencies.join(modules, on=["fact_order", "fact_id"], how="inner")

    def modules(self) -> pl.LazyFrame:
        """Return every module with its instability, abstractness, and distance."""
        total_coupling = pl.col("afferent_count") + pl.col("efferent_count")
        instability = (
            pl.when(total_coupling > 0)
            .then(pl.col("efferent_count") / total_coupling)
            .otherwise(0.0)
            .alias("instability")
        )
        abstractness = (
            pl.when(pl.col("declaration_count") > 0)
            .then(pl.col("abstract_declaration_count") / pl.col("declaration_count"))
            .otherwise(0.0)
            .alias("abstractness")
        )
        return (
            self.facts()
            .with_columns(instability, abstractness)
            .with_columns(
                (pl.col("abstractness") + pl.col("instability") - 1.0).abs().alias("distance")
            )
        )


def counted_text(amount: pl.Expr, singular: str) -> pl.Expr:
    """Render one relational count with its correctly inflected noun."""
    return pl.concat_str(
        amount,
        pl.when(amount == 1).then(pl.lit(f" {singular}")).otherwise(pl.lit(f" {singular}s")),
    )


def percentage_text(value: pl.Expr) -> pl.Expr:
    """Render a percentage with the rule's three significant figures."""
    return (value * 100.0).round_sig_figs(3).cast(pl.String).str.replace(r"\.0$", "")
