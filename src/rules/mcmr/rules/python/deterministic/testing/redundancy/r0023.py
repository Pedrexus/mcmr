import polars as pl
from pydantic import PositiveInt

from ...... import rule
from ......facts import TestFunctionFact
from ......query import CountQuery
from ......table import Table
from ..relations import test_cluster_query
from ..testfunctions import TestFunctionTables


@rule("PY-TEST0015")
def duplicate_test_intent_cluster_count(
    subject: Table[TestFunctionFact],
    *,
    minimum_tests: PositiveInt = 2,
) -> CountQuery:
    """Count tests that repeat the same body, data, fixtures, and production reach.

    Definition
    ----------
    Resolve every collected test through the repository call graph. Follow test helpers until the
    graph reaches production declarations, then group tests only when their complete reachable
    declaration set, literal-neutral body, literal vector, and fixture closure are identical. A
    group containing at least `minimum_tests` tests is one duplicate intent cluster.

    Evidence
    --------
    Each finding names every duplicate test and reports the test count and shared production graph
    point count. The default requires two exact duplicates. The value is the number of clusters,
    not the number of tests in them.

    Exceptions
    ----------
    Tests with no statically reachable production declaration abstain. Different literals,
    fixtures, assertion structure, control flow, or reachable declarations keep tests separate.
    Dynamic dispatch can leave a static graph incomplete, so this rule never deletes a test and
    offers no automatic repair.

    Examples
    --------
    Bad
    ~~~
    Two parser tests have the same body, values, fixtures, and reachable production declarations,
    so they form `1` cluster.

    Good
    ~~~~
    An invalid-input test expects a different result and reaches the parser error path, so it stays
    separate and the duplicate cluster value is `0`.

    References
    ----------
    Cites "xUnit Test Patterns", test code duplication
    Cites "Growing Object-Oriented Software, Guided by Tests", maintaining test intent
    """
    relations = TestFunctionTables(subject)
    tests = relations.behaviors().filter(pl.col("reachable_targets").list.len() > 0)
    selected = (
        tests.group_by(
            "body_shape",
            "literal_values",
            "fixture_names",
            "reachable_targets",
            maintain_order=True,
        )
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
        )
        .filter(pl.col("test_count") >= minimum_tests)
        .with_columns(
            pl.col("reachable_targets").list.len().cast(pl.UInt64).alias("target_count"),
            pl.lit(1, dtype=pl.UInt64).alias("intent_count"),
            pl.concat_str(
                pl.lit("duplicate test intent reaches the same production graph in `"),
                pl.col("test_names").list.join("`, `"),
                pl.lit("`"),
            ).alias("message"),
        )
    )
    return test_cluster_query(relations, selected)
