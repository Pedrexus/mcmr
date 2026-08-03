import polars as pl

from .....query import CountQuery, FindingQuery, OccurrenceQuery, RuleQuery


def count_query(frame: pl.LazyFrame, measurement: str) -> CountQuery:
    """Return the standard exact count query for a module relation."""
    value = pl.col("value")
    return RuleQuery.integer(
        frame,
        value,
        findings=FindingQuery.precise_integer(
            frame,
            value,
            measurement,
            evidence=pl.col("evidence"),
        ),
    )


def occurrence_query(frame: pl.LazyFrame, measurement: str) -> OccurrenceQuery:
    """Return the standard exact occurrence query for every module."""
    value = pl.col("value")
    return RuleQuery.boolean(
        frame,
        value,
        findings=FindingQuery.precise_boolean(
            frame,
            value,
            measurement,
            evidence=pl.col("evidence"),
        ),
    )
