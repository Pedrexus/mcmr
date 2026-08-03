import polars as pl


def span_columns(source: pl.LazyFrame) -> list[pl.Expr]:
    """Return normalized unsigned source span columns for one finding relation."""
    columns = set(source.collect_schema().names())
    return [
        (pl.col(name) if name in columns else pl.lit(1 if name.endswith("line") else 0))
        .cast(pl.UInt64)
        .alias(name)
        for name in ("start_line", "start_column", "end_line", "end_column")
    ]


def provenance_columns(source: pl.LazyFrame) -> list[pl.Expr]:
    """Return model provenance columns or deterministic empty defaults."""
    columns = set(source.collect_schema().names())
    defaults: list[tuple[str, pl.DataType | type[pl.DataType], str | int]] = [
        ("provenance_backend", pl.String, ""),
        ("provenance_model", pl.String, ""),
        ("provenance_reasoning_effort", pl.String, ""),
        ("provenance_input_tokens", pl.UInt64, 0),
        ("provenance_cached_input_tokens", pl.UInt64, 0),
        ("provenance_output_tokens", pl.UInt64, 0),
        ("provenance_reasoning_tokens", pl.UInt64, 0),
    ]
    return [
        (pl.col(name) if name in columns else pl.lit(default, dtype=dtype)).alias(name)
        for name, dtype, default in defaults
    ]
