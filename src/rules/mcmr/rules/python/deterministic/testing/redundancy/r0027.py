import polars as pl
from pydantic import PositiveInt

from ...... import rule
from ......facts import TestFunctionFact
from ......query import CountQuery
from ......table import Table
from ..relations import test_cluster_query
from ..testfunctions import TestFunctionTables


@rule("PY-TEST0019")
def production_reach_hotspot_count(
    subject: Table[TestFunctionFact],
    *,
    minimum_tests: PositiveInt = 8,
) -> CountQuery:
    """Count production declarations reached repeatedly by low-diversity tests.

    Definition
    ----------
    Explode each collected test's transitive production reach into individual declarations. Group
    tests by declaration and report a group with at least `minimum_tests` tests when the number of
    distinct literal-neutral bodies is no more than half the test count. This is a static
    over-coverage hotspot where parametrization, a generated property, or consolidation deserves
    review even when the tests reach different secondary declarations.

    Evidence
    --------
    Each finding names the shared production declaration and the tests that reach it. Measurements
    report test count, one shared target, and distinct body count. `PY-TEST0016` remains the
    stronger signal for tests whose complete reachable declaration sets are identical. The value
    is the number of low-diversity production reach hotspots.

    Exceptions
    ----------
    Unresolved tests abstain. A declaration with mostly distinct test bodies remains valid. A
    shared facade, constructor, protocol method, or error type can legitimately have broad reach,
    so this rule requests review and offers no automatic deletion or rewrite.

    Examples
    --------
    Bad
    ~~~
    Ten `test_parse_*` cases reach one parser through four repeated body shapes, so the value is
    `1`.

    Good
    ~~~~
    Ten `test_protocol_*` cases use eight distinct bodies, so the value remains `0`.

    References
    ----------
    Cites "Software Testing and Analysis", graph coverage criteria
    Cites "Growing Object-Oriented Software, Guided by Tests", maintaining test intent
    """
    relations = TestFunctionTables(subject)
    selected = (
        relations.behaviors()
        .filter(pl.col("reachable_targets").list.len() > 0)
        .explode("reachable_targets", empty_as_null=True)
        .group_by("reachable_targets", maintain_order=True)
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
            & (pl.col("intent_count") * 2 <= pl.col("test_count"))
        )
        .with_columns(
            pl.lit(1, dtype=pl.UInt64).alias("target_count"),
            pl.concat_str(
                pl.lit("low-diversity tests repeatedly reach `"),
                pl.col("reachable_targets"),
                pl.lit("` through `"),
                pl.col("test_names").list.join("`, `"),
                pl.lit("`"),
            ).alias("message"),
        )
    )
    return test_cluster_query(relations, selected)
