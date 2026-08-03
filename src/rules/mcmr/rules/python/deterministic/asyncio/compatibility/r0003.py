import polars as pl
from pydantic import NonNegativeInt

from ...... import rule
from ......domain.contracts import Unit
from ......facts import CallFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import CallRelation, Table

_DEPRECATED_POLICY_APIS = {
    "asyncio.get_event_loop_policy",
    "asyncio.set_event_loop_policy",
    "asyncio.AbstractEventLoopPolicy",
    "asyncio.DefaultEventLoopPolicy",
    "asyncio.WindowsSelectorEventLoopPolicy",
    "asyncio.WindowsProactorEventLoopPolicy",
}


@rule("PY-ASYN0003")
def deprecated_event_loop_policy_usage(
    subject: Table[CallFact],
    *,
    python_minor: NonNegativeInt = 14,
) -> CountQuery:
    """Count event-loop policy APIs deprecated in Python 3.14.

    Definition
    ----------
    For a configured minimum Python 3 minor version of 14 or newer, resolve references to
    `get_event_loop_policy`, `set_event_loop_policy`, `AbstractEventLoopPolicy`,
    `DefaultEventLoopPolicy`, `WindowsSelectorEventLoopPolicy`, and
    `WindowsProactorEventLoopPolicy`. The value and findings count every reference.

    Evidence
    --------
    Every finding gives the deprecated asyncio member and its exact source range. The value is the
    number of deprecated policy references.

    Exceptions
    ----------
    A compatibility layer supporting older Python may temporarily retain policy code behind a
    version boundary. Python 3.14 applications should configure loops through `loop_factory` on
    `asyncio.run` or `asyncio.Runner`. No automatic rewrite is safe because policy subclasses can
    own arbitrary process-wide behavior. `python_minor` is the Python 3 minor version the project
    targets, and the rule reports nothing below 14 because these names are not deprecated there.

    Examples
    --------
    `asyncio.set_event_loop_policy(CustomPolicy())` is reported for Python 3.14. Passing
    `loop_factory=uvloop.new_event_loop` to one runner is accepted. A Python 3.13 configuration
    produces no finding.

    References
    ----------
    Cites "The Python Standard Library", asyncio policy deprecations
    https://docs.python.org/3/library/asyncio-policy.html
    Cites "The Python Standard Library", asyncio runners and `loop_factory`
    https://docs.python.org/3/library/asyncio-runner.html
    """
    facts = subject.lazy(CallRelation.FACTS)
    evidence = (
        subject.lazy(CallRelation.EVIDENCE)
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("signal").sort_by("ordinal").alias("evidence"))
    )
    selected = (
        subject.lazy(CallRelation.CALLS)
        .join(facts.select("fact_id"), on="fact_id", how="inner")
        .filter(
            pl.lit(python_minor >= 14) & pl.col("qualified_name").is_in(_DEPRECATED_POLICY_APIS)
        )
    )
    counts = selected.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("value")
    )
    frame = facts.join(counts, on="fact_id", how="left").with_columns(pl.col("value").fill_null(0))
    finding_rows = (
        selected.select(
            "fact_id",
            "ordinal",
            "qualified_name",
            pl.col("node_path").alias("path"),
            pl.col("node_start_line").alias("start_line"),
            pl.col("node_start_column").alias("start_column"),
            pl.col("node_end_line").alias("end_line"),
            pl.col("node_end_column").alias("end_column"),
        )
        .join(evidence, on="fact_id", how="left")
        .with_columns(pl.col("evidence").fill_null(pl.lit([], dtype=pl.List(pl.String))))
    )
    value = pl.col("value")
    return RuleQuery.integer(
        frame,
        value,
        findings=FindingQuery.build(
            finding_rows,
            pl.concat_str(
                pl.lit("`"),
                pl.col("qualified_name"),
                pl.lit("` is an event-loop policy API deprecated in Python 3.14"),
            ),
            (("deprecated event loop policy usage", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
    )
