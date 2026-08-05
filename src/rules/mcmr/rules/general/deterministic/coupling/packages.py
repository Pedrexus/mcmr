from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from .relations import CouplingRelations


class PackageCoupling:
    """Aggregate module import edges into Martin's package coupling graph."""

    def __init__(self, relations: CouplingRelations) -> None:
        self.relations = relations

    @staticmethod
    def package(column: str, *, path: str | None = None) -> pl.Expr:
        """Return the enclosing package of one language-neutral module name."""
        normalized = (
            pl.col(column)
            .str.replace_all("::", ".", literal=True)
            .str.replace_all("/", ".", literal=True)
        )
        enclosing = normalized.str.replace(r"\.[^.]+$", "")
        if path is None:
            return enclosing
        package_module = pl.col(path).str.ends_with("__init__.py") | pl.col(path).str.ends_with(
            "mod.rs"
        )
        return pl.when(package_module).then(normalized).otherwise(enclosing)

    @staticmethod
    def test_path(column: str) -> pl.Expr:
        """Recognize conventional test and specification source paths."""
        return pl.col(column).str.contains(r"(^|/)(tests?|specs?)(/|$)") | pl.col(
            column
        ).str.contains(r"(^|[._-])(test|spec)\.[^.]+$")

    def counted(self, selected: pl.LazyFrame) -> pl.LazyFrame:
        """Attach each selected outgoing edge count to its package."""
        counts = selected.group_by("module", maintain_order=True).agg(
            pl.len().cast(pl.UInt64).alias("value")
        )
        return (
            self.packages()
            .join(counts, on="module", how="left")
            .with_columns(pl.col("value").fill_null(0))
        )

    def dependencies(self) -> pl.LazyFrame:
        """Return each package edge beside both package instability values."""
        sources = self.metrics().select(
            "module",
            "instability",
            "afferent_count",
            "efferent_count",
        )
        targets = self.metrics().rename(
            {
                "module": "dependency_module",
                "instability": "dependency_instability",
                "afferent_count": "dependency_afferent_count",
                "efferent_count": "dependency_efferent_count",
            }
        )
        locations = self.locations().select(
            "module",
            pl.col("fact_order").alias("result_fact_order"),
            pl.col("fact_id").alias("result_fact_id"),
        )
        return (
            self.edges()
            .join(sources, on="module", how="inner")
            .join(targets, on="dependency_module", how="inner")
            .join(locations, on="module", how="inner")
            .drop("fact_order", "fact_id")
            .rename(
                {
                    "result_fact_order": "fact_order",
                    "result_fact_id": "fact_id",
                }
            )
        )

    def edges(self) -> pl.LazyFrame:
        """Return unique imports crossing from one package into another."""
        targets = self.relations.modules().select(
            pl.col("module").alias("dependency_module"),
            self.package("module", path="path").alias("dependency_package"),
            pl.col("path").alias("dependency_path"),
        )
        return (
            self.relations.dependencies()
            .filter(
                ~pl.col("path").str.ends_with("__init__.py")
                & ~pl.col("path").str.ends_with("mod.rs")
            )
            .with_columns(self.package("module", path="path").alias("module"))
            .join(targets, on="dependency_module", how="inner")
            .filter(~(self.test_path("path") & ~self.test_path("dependency_path")))
            .filter(pl.col("module") != pl.col("dependency_package"))
            .select(
                "fact_order",
                "fact_id",
                "ordinal",
                "path",
                "start_line",
                "start_column",
                "end_line",
                "end_column",
                "language",
                "evidence",
                "dependency_path",
                "module",
                pl.col("dependency_package").alias("dependency_module"),
            )
            .unique(["module", "dependency_module"], keep="first", maintain_order=True)
        )

    def locations(self) -> pl.LazyFrame:
        """Return one stable representative source location for every package."""
        return (
            self.relations.modules()
            .with_columns(self.package("module", path="path").alias("module"))
            .group_by("module", maintain_order=True)
            .agg(
                pl.col("fact_order").first(),
                pl.col("fact_id").first(),
                pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
                pl.col("path").first(),
                pl.col("start_line").first(),
                pl.col("start_column").first(),
                pl.col("end_line").first(),
                pl.col("end_column").first(),
                pl.col("language").first(),
                pl.col("evidence").first(),
            )
        )

    def metrics(self) -> pl.LazyFrame:
        """Return afferent, efferent, and instability values for every package."""
        edges = self.edges()
        components = pl.concat(
            [
                self.relations.modules().select(
                    self.package("module", path="path").alias("module")
                ),
                edges.select(pl.col("dependency_module").alias("module")),
            ]
        ).unique("module", maintain_order=True)
        outgoing = edges.group_by("module", maintain_order=True).agg(
            pl.col("dependency_module").n_unique().cast(pl.UInt64).alias("efferent_count")
        )
        incoming = (
            edges.group_by("dependency_module", maintain_order=True)
            .agg(pl.col("module").n_unique().cast(pl.UInt64).alias("afferent_count"))
            .rename({"dependency_module": "module"})
        )
        total = pl.col("afferent_count") + pl.col("efferent_count")
        return (
            components.join(incoming, on="module", how="left")
            .join(outgoing, on="module", how="left")
            .with_columns(
                pl.col("afferent_count").fill_null(0),
                pl.col("efferent_count").fill_null(0),
            )
            .with_columns((pl.col("efferent_count") / total).alias("instability"))
        )

    def packages(self) -> pl.LazyFrame:
        """Return every source package with its metrics and representative location."""
        return self.locations().join(self.metrics(), on="module", how="inner")
