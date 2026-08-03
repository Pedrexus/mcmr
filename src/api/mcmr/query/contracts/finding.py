from typing import TYPE_CHECKING

import polars as pl
from patos import FrozenModel, Runtime

from ..expressions import provenance_columns, span_columns

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ...domain.primitives import Unit


class FindingQuery(FrozenModel):
    """Carry normalized finding rows produced by one table rule."""

    rows: Runtime[pl.LazyFrame]

    @classmethod
    def build(
        cls,
        source: pl.LazyFrame,
        message: pl.Expr,
        measurements: Sequence[tuple[str, pl.Expr, Unit]],
        *,
        predicate: pl.Expr | None = None,
        finding_order: pl.Expr | None = None,
        question: str | pl.Expr = "",
        options: Sequence[str] = (),
        evidence: pl.Expr | None = None,
    ) -> FindingQuery:
        """Build normalized finding rows from relational message and measurement expressions."""
        rows = source if predicate is None else source.filter(predicate)
        choice = pl.lit(question) if isinstance(question, str) else question
        return cls(
            rows=rows.select(
                "fact_id",
                (
                    pl.lit(0, dtype=pl.UInt64)
                    if finding_order is None
                    else finding_order.cast(pl.UInt64)
                ).alias("finding_order"),
                message.alias("message"),
                "path",
                *span_columns(source),
                pl.lit(
                    [name for name, _, _ in measurements],
                    dtype=pl.List(pl.String),
                ).alias("measurement_names"),
                (
                    pl.concat_list(*[value.cast(pl.Float64) for _, value, _ in measurements])
                    if measurements
                    else pl.lit([], dtype=pl.List(pl.Float64))
                ).alias("measurement_values"),
                pl.lit(
                    [str(unit) for _, _, unit in measurements],
                    dtype=pl.List(pl.String),
                ).alias("measurement_units"),
                (pl.lit([], dtype=pl.List(pl.String)) if evidence is None else evidence).alias(
                    "evidence"
                ),
                choice.alias("choice_question"),
                pl.lit(list(options), dtype=pl.List(pl.String)).alias("choice_options"),
                *provenance_columns(source),
            )
        )

    @classmethod
    def empty(cls) -> FindingQuery:
        """Return an empty relation with the stable finding schema."""
        return cls(
            rows=pl.DataFrame(
                schema={
                    "fact_id": pl.String,
                    "finding_order": pl.UInt64,
                    "message": pl.String,
                    "path": pl.String,
                    "start_line": pl.UInt64,
                    "start_column": pl.UInt64,
                    "end_line": pl.UInt64,
                    "end_column": pl.UInt64,
                    "measurement_names": pl.List(pl.String),
                    "measurement_values": pl.List(pl.Float64),
                    "measurement_units": pl.List(pl.String),
                    "evidence": pl.List(pl.String),
                    "choice_question": pl.String,
                    "choice_options": pl.List(pl.String),
                    "provenance_backend": pl.String,
                    "provenance_model": pl.String,
                    "provenance_reasoning_effort": pl.String,
                    "provenance_input_tokens": pl.UInt64,
                    "provenance_cached_input_tokens": pl.UInt64,
                    "provenance_output_tokens": pl.UInt64,
                    "provenance_reasoning_tokens": pl.UInt64,
                }
            ).lazy()
        )

    @classmethod
    def precise_boolean(
        cls,
        source: pl.LazyFrame,
        value: pl.Expr,
        measurement: str,
        *,
        question: str = "",
        options: Sequence[str] = (),
        evidence: pl.Expr | None = None,
    ) -> FindingQuery:
        """State one standard occurrence finding for every true value row."""
        return cls(
            rows=source.filter(value).select(
                "fact_id",
                pl.lit(0, dtype=pl.UInt64).alias("finding_order"),
                pl.concat_str(
                    pl.lit("`"),
                    pl.col("fact_id"),
                    pl.lit(f"` satisfies {measurement}"),
                ).alias("message"),
                "path",
                *span_columns(source),
                pl.lit([measurement], dtype=pl.List(pl.String)).alias("measurement_names"),
                pl.lit([1.0], dtype=pl.List(pl.Float64)).alias("measurement_values"),
                pl.lit(["count"], dtype=pl.List(pl.String)).alias("measurement_units"),
                (pl.lit([], dtype=pl.List(pl.String)) if evidence is None else evidence).alias(
                    "evidence"
                ),
                pl.lit(question).alias("choice_question"),
                pl.lit(list(options), dtype=pl.List(pl.String)).alias("choice_options"),
            )
        )

    @classmethod
    def precise_category(
        cls,
        source: pl.LazyFrame,
        value: pl.Expr,
        measurement: str,
        *,
        question: str = "",
        options: Sequence[str] = (),
        evidence: pl.Expr | None = None,
    ) -> FindingQuery:
        """State one standard categorical finding for every value row."""
        return cls(
            rows=source.select(
                "fact_id",
                pl.lit(0, dtype=pl.UInt64).alias("finding_order"),
                pl.concat_str(
                    pl.lit(f"{measurement} is `"),
                    value.cast(pl.String),
                    pl.lit("` for `"),
                    pl.col("fact_id"),
                    pl.lit("`"),
                ).alias("message"),
                "path",
                *span_columns(source),
                pl.lit([], dtype=pl.List(pl.String)).alias("measurement_names"),
                pl.lit([], dtype=pl.List(pl.Float64)).alias("measurement_values"),
                pl.lit([], dtype=pl.List(pl.String)).alias("measurement_units"),
                (pl.lit([], dtype=pl.List(pl.String)) if evidence is None else evidence).alias(
                    "evidence"
                ),
                pl.lit(question).alias("choice_question"),
                pl.lit(list(options), dtype=pl.List(pl.String)).alias("choice_options"),
            )
        )

    @classmethod
    def precise_float(
        cls,
        source: pl.LazyFrame,
        value: pl.Expr,
        measurement: str,
        unit: Unit,
        *,
        question: str = "",
        options: Sequence[str] = (),
        evidence: pl.Expr | None = None,
    ) -> FindingQuery:
        """State one standard floating-point measurement finding for every value row."""
        return cls(
            rows=source.select(
                "fact_id",
                pl.lit(0, dtype=pl.UInt64).alias("finding_order"),
                pl.concat_str(
                    pl.lit(f"{measurement} is "),
                    value.cast(pl.String),
                    pl.lit(" for `"),
                    pl.col("fact_id"),
                    pl.lit("`"),
                ).alias("message"),
                "path",
                *span_columns(source),
                pl.lit([measurement], dtype=pl.List(pl.String)).alias("measurement_names"),
                pl.concat_list(value.cast(pl.Float64)).alias("measurement_values"),
                pl.lit([str(unit)], dtype=pl.List(pl.String)).alias("measurement_units"),
                (pl.lit([], dtype=pl.List(pl.String)) if evidence is None else evidence).alias(
                    "evidence"
                ),
                pl.lit(question).alias("choice_question"),
                pl.lit(list(options), dtype=pl.List(pl.String)).alias("choice_options"),
            )
        )

    @classmethod
    def precise_integer(
        cls,
        source: pl.LazyFrame,
        value: pl.Expr,
        measurement: str,
        *,
        question: str = "",
        options: Sequence[str] = (),
        evidence: pl.Expr | None = None,
    ) -> FindingQuery:
        """State one standard integer measurement finding for every value row."""
        return cls(
            rows=source.select(
                "fact_id",
                pl.lit(0, dtype=pl.UInt64).alias("finding_order"),
                pl.concat_str(
                    pl.lit(f"{measurement} is "),
                    value.cast(pl.String),
                    pl.lit(" for `"),
                    pl.col("fact_id"),
                    pl.lit("`"),
                ).alias("message"),
                "path",
                *span_columns(source),
                pl.lit([measurement], dtype=pl.List(pl.String)).alias("measurement_names"),
                pl.concat_list(value.cast(pl.Float64)).alias("measurement_values"),
                pl.lit(["count"], dtype=pl.List(pl.String)).alias("measurement_units"),
                (pl.lit([], dtype=pl.List(pl.String)) if evidence is None else evidence).alias(
                    "evidence"
                ),
                pl.lit(question).alias("choice_question"),
                pl.lit(list(options), dtype=pl.List(pl.String)).alias("choice_options"),
            )
        )

    def normalized(self) -> FindingQuery:
        """Add stable optional columns shared by deterministic and contextual findings."""
        return FindingQuery(rows=self.rows.with_columns(*provenance_columns(self.rows)))
