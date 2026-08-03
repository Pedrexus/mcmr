import polars as pl

from .....query import CountQuery, FindingQuery, OccurrenceQuery, RuleQuery


def count_query(frame: pl.LazyFrame, measurement: str) -> CountQuery:
    """Return one exact count and its standard source-level finding."""
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
    """Return one exact occurrence and its standard source-level finding."""
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
