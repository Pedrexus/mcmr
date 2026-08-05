import polars as pl
from pydantic import PositiveInt

from ...... import rule
from ......facts import TestFunctionFact
from ......query import CountQuery
from ......table import Table
from ..relations import test_cluster_query
from ..testfunctions import TestFunctionTables


@rule("PY-TEST0016")
def concentrated_test_reach_cluster_count(
    subject: Table[TestFunctionFact],
    *,
    minimum_tests: PositiveInt = 4,
) -> CountQuery:
    """Count production graph reach clusters with repeated test intent.

    Definition
    ----------
    Treat the transitively reachable production declarations of one collected test as its static
    graph coverage set. Group tests with the same set and fixture closure. Report a group with at
    least `minimum_tests` tests when more than one literal-neutral body exists but the distinct
    body count is no more than half the test count. The repeated bodies are zero-marginal static
    coverage inside that cluster and are candidates for consolidation or parametrization.

    Evidence
    --------
    Each finding lists the tests and measures test count, reachable production declarations, and
    distinct literal-neutral bodies. This exposes both over-coverage concentration and behavioral
    diversity instead of claiming that a popular production function is redundant merely because
    many tests reach it. The value is the number of concentrated reach clusters.

    Exceptions
    ----------
    A cluster with no production reach abstains. Exact duplicate bodies belong to `PY-TEST0015`.
    A cluster where most tests state distinct bodies is diverse and remains valid. Runtime-only
    dispatch, native calls, and data-dependent branches can add coverage the static graph cannot
    prove, so the finding requests review and has no automatic repair.

    Examples
    --------
    Bad
    ~~~
    Six `test_parse_*` cases reach the same four production declarations through two repeated body
    shapes, so the value is `1`.

    Good
    ~~~~
    Six `test_protocol_*` cases have six distinct body shapes, so the value remains `0`.

    References
    ----------
    Cites "Software Testing and Analysis", graph coverage criteria
    Cites "xUnit Test Patterns", test code duplication
    """
    relations = TestFunctionTables(subject)
    selected = (
        relations.behaviors()
        .filter(pl.col("reachable_targets").list.len() > 0)
        .group_by("fixture_names", "reachable_targets", maintain_order=True)
        .agg(
            pl.col("fact_id").first(),
            pl.col("ordinal").first(),
            pl.col("path").first(),
            pl.col("node.span.start_line").first().alias("start_line"),
            pl.col("node.span.start_column").first().alias("start_column"),
            pl.col("node.span.end_line").first().alias("end_line"),
            pl.col("node.span.end_column").first().alias("end_column"),
            pl.col("name").sort().alias("test_names"),
            pl.len().cast(pl.UInt64).alias("test_count"),
            pl.col("body_shape").n_unique().cast(pl.UInt64).alias("intent_count"),
        )
        .filter(
            (pl.col("test_count") >= minimum_tests)
            & (pl.col("intent_count") > 1)
            & (pl.col("intent_count") * 2 <= pl.col("test_count"))
        )
        .with_columns(
            pl.col("reachable_targets").list.len().cast(pl.UInt64).alias("target_count"),
            pl.concat_str(
                pl.lit("repeated test intent concentrates the same production reach across `"),
                pl.col("test_names").list.join("`, `"),
                pl.lit("`"),
            ).alias("message"),
        )
    )
    return test_cluster_query(relations, selected)
