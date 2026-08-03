import polars as pl

from .....domain.contracts import Unit
from .....facts import (
    DataChangeFact,
)
from .....query import CountQuery, FindingQuery, PercentageQuery, RuleQuery
from .....table.relations import FactRelations


class DataChangeTables(FactRelations[DataChangeFact]):
    """Expose breaking changes and their normalized impact evidence."""

    def breaking(self) -> pl.LazyFrame:
        """Return only changes the provider declared breaking."""
        return self.changes().filter(pl.col("is_breaking"))

    def changes(self) -> pl.LazyFrame:
        """Return every retained data change."""
        return self.records("changes")

    def impacted(self) -> pl.LazyFrame:
        """Return distinct changed asset and impacted asset pairs."""
        breaking = self.breaking().select("fact_id", "record_id", "asset_identifier")
        changed_assets = breaking.select(
            "fact_id",
            "asset_identifier",
            pl.col("asset_identifier").alias("affected_asset"),
        )
        downstream = (
            self.values("changes.downstream_assets")
            .join(
                breaking,
                left_on=["fact_id", "parent_id"],
                right_on=["fact_id", "record_id"],
                how="inner",
            )
            .select(
                "fact_id",
                "asset_identifier",
                pl.col("string_value").alias("affected_asset"),
            )
        )
        return pl.concat([changed_assets, downstream]).unique(
            ["fact_id", "asset_identifier", "affected_asset"],
            maintain_order=True,
        )

    def tested(self) -> pl.LazyFrame:
        """Return distinct changed asset and tested asset pairs for breaking changes."""
        breaking = self.breaking().select("fact_id", "record_id", "asset_identifier")
        return (
            self.values("changes.tested_assets")
            .join(
                breaking,
                left_on=["fact_id", "parent_id"],
                right_on=["fact_id", "record_id"],
                how="inner",
            )
            .select(
                "fact_id",
                "asset_identifier",
                pl.col("string_value").alias("affected_asset"),
            )
            .unique(
                ["fact_id", "asset_identifier", "affected_asset"],
                maintain_order=True,
            )
        )


def count_query(frame: pl.LazyFrame, measurement: str) -> CountQuery:
    """Return one precise fact-level count and its retained evidence."""
    value = pl.col("value")
    return RuleQuery.integer(
        frame,
        value,
        findings=FindingQuery.build(
            frame,
            pl.concat_str(
                pl.lit(f"{measurement} is "),
                _four_significant_digits(value),
                pl.lit(" for `"),
                pl.col("fact_id"),
                pl.lit("`"),
            ),
            ((measurement, value, Unit.COUNT),),
            evidence=pl.col("evidence"),
        ),
    )


def percentage_query(frame: pl.LazyFrame, measurement: str) -> PercentageQuery:
    """Return one precise fact-level percentage and its retained evidence."""
    value = pl.col("value")
    return RuleQuery.floating(
        frame,
        value,
        findings=FindingQuery.build(
            frame,
            pl.concat_str(
                pl.lit(f"{measurement} is "),
                _four_significant_digits(value),
                pl.lit(" percent for `"),
                pl.col("fact_id"),
                pl.lit("`"),
            ),
            ((measurement, value, Unit.PERCENTAGE),),
            evidence=pl.col("evidence"),
        ),
    )


def _four_significant_digits(value: pl.Expr) -> pl.Expr:
    """Format a nonnegative measurement with four significant digits."""
    rounded = _rounded_measurement(value.cast(pl.Float64))
    exponent, scientific = _scientific_notation(rounded)
    return (
        pl.when(rounded == 0)
        .then(pl.lit("0"))
        .when((exponent < -4) | (exponent >= 4))
        .then(scientific)
        .otherwise(rounded.cast(pl.String).str.replace(r"\.0$", ""))
    )


def _rounded_measurement(number: pl.Expr) -> pl.Expr:
    """Round one numeric expression to four significant digits."""
    magnitude = pl.when(number == 0).then(1.0).otherwise(number.abs())
    initial_exponent = magnitude.log(10).floor().cast(pl.Int64)
    fixed = number
    for exponent_value in range(-4, 4):
        fixed = (
            pl.when(initial_exponent == exponent_value)
            .then(number.round(3 - exponent_value, mode="half_to_even"))
            .otherwise(fixed)
        )
    initial_mantissa = (number / pl.lit(10.0).pow(initial_exponent)).round(3, mode="half_to_even")
    crossed_boundary = initial_mantissa.abs() >= 10
    scientific_exponent = initial_exponent + crossed_boundary.cast(pl.Int64)
    scientific_mantissa = (
        pl.when(crossed_boundary).then(initial_mantissa / 10.0).otherwise(initial_mantissa)
    )
    return (
        pl.when(initial_exponent.is_between(-4, 3))
        .then(fixed)
        .otherwise(scientific_mantissa * pl.lit(10.0).pow(scientific_exponent))
    )


def _scientific_notation(rounded: pl.Expr) -> tuple[pl.Expr, pl.Expr]:
    """Return the base-ten exponent and normalized notation for one rounded value."""
    rounded_magnitude = pl.when(rounded == 0).then(1.0).otherwise(rounded.abs())
    exponent = rounded_magnitude.log(10).floor().cast(pl.Int64)
    exponent_digits = exponent.abs().cast(pl.String)
    mantissa = (rounded / pl.lit(10.0).pow(exponent)).round(3, mode="half_to_even")
    scientific = pl.concat_str(
        mantissa.cast(pl.String).str.replace(r"\.0$", ""),
        pl.lit("e"),
        pl.when(exponent < 0).then(pl.lit("-")).otherwise(pl.lit("+")),
        pl.when(exponent.abs() < 10)
        .then(pl.concat_str(pl.lit("0"), exponent_digits))
        .otherwise(exponent_digits),
    )
    return exponent, scientific
