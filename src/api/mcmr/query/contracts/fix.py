import polars as pl
from patos import FrozenModel, Runtime


class FixQuery(FrozenModel):
    """Carry one table rule's normalized rewrite program."""

    summary: str
    rewrites: Runtime[pl.LazyFrame]
    nodes: Runtime[pl.LazyFrame]
    imports: Runtime[pl.LazyFrame]

    @staticmethod
    def empty_imports() -> pl.LazyFrame:
        """Return the stable empty requested-import relation."""
        return pl.DataFrame(
            schema={
                "fact_id": pl.String,
                "rewrite_order": pl.UInt64,
                "ordinal": pl.UInt64,
                "module": pl.String,
                "name": pl.String,
                "alias": pl.String,
                "level": pl.UInt64,
                "type_only": pl.Boolean,
            }
        ).lazy()

    @staticmethod
    def empty_nodes() -> pl.LazyFrame:
        """Return the stable empty rewrite node relation."""
        return pl.DataFrame(
            schema={
                "fact_id": pl.String,
                "rewrite_order": pl.UInt64,
                "role": pl.String,
                "ordinal": pl.UInt64,
                "id": pl.String,
                "path": pl.String,
                "start_line": pl.UInt64,
                "start_column": pl.UInt64,
                "end_line": pl.UInt64,
                "end_column": pl.UInt64,
                "kind": pl.String,
                "text": pl.String,
            }
        ).lazy()

    @staticmethod
    def empty_rewrites() -> pl.LazyFrame:
        """Return the stable empty rewrite relation."""
        return pl.DataFrame(
            schema={
                "fact_id": pl.String,
                "rewrite_order": pl.UInt64,
                "kind": pl.String,
                "source": pl.String,
                "placement": pl.String,
                "name": pl.String,
                "symbol_id": pl.String,
                "symbol_name": pl.String,
                "references_complete": pl.Boolean,
            }
        ).lazy()

    @classmethod
    def build(
        cls,
        summary: str,
        *,
        rewrites: pl.LazyFrame,
        nodes: pl.LazyFrame | None = None,
        imports: pl.LazyFrame | None = None,
    ) -> FixQuery:
        """Build one rewrite query whose relations share one concrete physical schema."""
        normalized_nodes = cls.empty_nodes() if nodes is None else nodes
        normalized_imports = cls.empty_imports() if imports is None else imports
        return cls(
            summary=summary,
            rewrites=rewrites.select(
                pl.col("fact_id").cast(pl.String),
                pl.col("rewrite_order").cast(pl.UInt64),
                pl.col("kind").cast(pl.String),
                pl.col("source").cast(pl.String),
                pl.col("placement").cast(pl.String),
                pl.col("name").cast(pl.String),
                pl.col("symbol_id").cast(pl.String),
                pl.col("symbol_name").cast(pl.String),
                pl.col("references_complete").cast(pl.Boolean),
            ),
            nodes=normalized_nodes.select(
                pl.col("fact_id").cast(pl.String),
                pl.col("rewrite_order").cast(pl.UInt64),
                pl.col("role").cast(pl.String),
                pl.col("ordinal").cast(pl.UInt64),
                pl.col("id").cast(pl.String),
                pl.col("path").cast(pl.String),
                pl.col("start_line").cast(pl.UInt64),
                pl.col("start_column").cast(pl.UInt64),
                pl.col("end_line").cast(pl.UInt64),
                pl.col("end_column").cast(pl.UInt64),
                pl.col("kind").cast(pl.String),
                pl.col("text").cast(pl.String),
            ),
            imports=normalized_imports.select(
                pl.col("fact_id").cast(pl.String),
                pl.col("rewrite_order").cast(pl.UInt64),
                pl.col("ordinal").cast(pl.UInt64),
                pl.col("module").cast(pl.String),
                pl.col("name").cast(pl.String),
                pl.col("alias").cast(pl.String),
                pl.col("level").cast(pl.UInt64),
                pl.col("type_only").cast(pl.Boolean),
            ),
        )
