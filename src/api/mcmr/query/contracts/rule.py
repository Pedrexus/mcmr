from typing import Annotated

import polars as pl
from patos import FrozenModel, Runtime

from ...domain.contracts import RuleValue, Unit
from .finding import FindingQuery
from .fix import FixQuery


class RuleQuery[Value: RuleValue = RuleValue](FrozenModel):
    """Carry one rule's lazy values and normalized findings before judgment."""

    values: Runtime[pl.LazyFrame]
    findings: FindingQuery | None = None
    fix: FixQuery | None = None

    @staticmethod
    def identity(source: pl.LazyFrame) -> list[str | pl.Expr]:
        """Select the stable fact identity and complete source span columns."""
        columns = set(source.collect_schema().names())
        return [
            "fact_order",
            "fact_id",
            "path",
            "language",
            *(
                name
                if name in columns
                else pl.lit(1 if name.endswith("line") else 0, dtype=pl.UInt64).alias(name)
                for name in ("start_line", "start_column", "end_line", "end_column")
            ),
        ]

    @classmethod
    def boolean(
        cls,
        source: pl.LazyFrame,
        value: pl.Expr,
        finding_count: pl.Expr | None = None,
        *,
        findings: FindingQuery | None = None,
        fix: FixQuery | None = None,
    ) -> RuleQuery[bool]:
        """Build the shared Boolean result schema over a fact relation."""
        count = value.cast(pl.UInt64) if finding_count is None else finding_count
        return RuleQuery[bool](
            values=source.select(
                *cls.identity(source),
                pl.lit(None, dtype=pl.UInt64).alias("integer_value"),
                value.alias("boolean_value"),
                pl.lit(None, dtype=pl.Float64).alias("float_value"),
                pl.lit(None, dtype=pl.String).alias("category_value"),
                count.cast(pl.UInt64).alias("finding_count"),
            ),
            findings=findings,
            fix=fix,
        )

    @classmethod
    def category[Category: str](
        cls,
        source: pl.LazyFrame,
        value: pl.Expr,
        finding_count: pl.Expr | None = None,
        *,
        findings: FindingQuery | None = None,
        fix: FixQuery | None = None,
    ) -> RuleQuery[Category]:
        """Build the shared categorical result schema over a fact relation."""
        count = pl.lit(1, dtype=pl.UInt64) if finding_count is None else finding_count
        return RuleQuery[Category](
            values=source.select(
                *cls.identity(source),
                pl.lit(None, dtype=pl.UInt64).alias("integer_value"),
                pl.lit(None, dtype=pl.Boolean).alias("boolean_value"),
                pl.lit(None, dtype=pl.Float64).alias("float_value"),
                value.cast(pl.String).alias("category_value"),
                count.cast(pl.UInt64).alias("finding_count"),
            ),
            findings=findings,
            fix=fix,
        )

    @classmethod
    def floating(
        cls,
        source: pl.LazyFrame,
        value: pl.Expr,
        finding_count: pl.Expr | None = None,
        *,
        findings: FindingQuery | None = None,
        fix: FixQuery | None = None,
    ) -> RuleQuery[float]:
        """Build the shared floating-point result schema over a fact relation."""
        count = pl.lit(1, dtype=pl.UInt64) if finding_count is None else finding_count
        return RuleQuery[float](
            values=source.select(
                *cls.identity(source),
                pl.lit(None, dtype=pl.UInt64).alias("integer_value"),
                pl.lit(None, dtype=pl.Boolean).alias("boolean_value"),
                value.cast(pl.Float64).alias("float_value"),
                pl.lit(None, dtype=pl.String).alias("category_value"),
                count.cast(pl.UInt64).alias("finding_count"),
            ),
            findings=findings,
            fix=fix,
        )

    @classmethod
    def integer(
        cls,
        source: pl.LazyFrame,
        value: pl.Expr,
        finding_count: pl.Expr | None = None,
        *,
        findings: FindingQuery | None = None,
        fix: FixQuery | None = None,
    ) -> RuleQuery[int]:
        """Build the shared integer result schema over a fact relation."""
        count = value if finding_count is None else finding_count
        return RuleQuery[int](
            values=source.select(
                *cls.identity(source),
                value.cast(pl.UInt64).alias("integer_value"),
                pl.lit(None, dtype=pl.Boolean).alias("boolean_value"),
                pl.lit(None, dtype=pl.Float64).alias("float_value"),
                pl.lit(None, dtype=pl.String).alias("category_value"),
                count.cast(pl.UInt64).alias("finding_count"),
            ),
            findings=findings,
            fix=fix,
        )


type CountQuery = Annotated[RuleQuery[int], Unit.COUNT]
type OccurrenceQuery = Annotated[RuleQuery[bool], Unit.COUNT]
type PercentageQuery = Annotated[RuleQuery[float], Unit.PERCENTAGE]
