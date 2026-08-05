from typing import TYPE_CHECKING

import polars as pl

from .....domain.contracts import Unit
from .....query import CountQuery, FindingQuery, OccurrenceQuery, RuleQuery

if TYPE_CHECKING:
    from .testfunctions import TestFunctionTables


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


def test_cluster_query(
    relations: TestFunctionTables,
    selected: pl.LazyFrame,
) -> CountQuery:
    """Build one count with exact test, production target, and intent cluster evidence."""
    return RuleQuery.integer(
        relations.counted(selected),
        pl.col("value"),
        findings=FindingQuery.build(
            selected,
            pl.col("message"),
            (
                ("tests in the cluster", pl.col("test_count"), Unit.COUNT),
                ("reachable production declarations", pl.col("target_count"), Unit.COUNT),
                ("distinct literal-neutral bodies", pl.col("intent_count"), Unit.COUNT),
            ),
            finding_order=pl.col("ordinal"),
        ),
    )
