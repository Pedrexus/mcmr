import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import CallFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import CallRelation, Table


@rule("PY-ASYN0001")
def asyncio_run_boundary(
    subject: Table[CallFact],
) -> CountQuery:
    """Measure `asyncio.run` calls and enforce a single synchronous boundary.

    Definition
    ----------
    Resolve module-qualified and directly imported `asyncio.run` calls. Return the count for this
    call fact. A separate policy can enforce one synchronous boundary. The retained call sites
    expose async ownership for a separate nested-boundary rule.

    Evidence
    --------
    Evidence gives every call location, its enclosing function when present, and total call count.
    The value is the number of resolved `asyncio.run` calls.

    Exceptions
    ----------
    Independent executables can each own one event-loop boundary. Provider selection and policy
    configuration define that layout. When one synchronous process genuinely needs several
    top-level async calls in the same context, use one `asyncio.Runner`. Tests and experiments can
    be omitted by provider selection. This rule has no automatic lifecycle rewrite.

    Examples
    --------
    One CLI calling `asyncio.run(main())` once returns `1`. Three library functions each calling
    `asyncio.run` return `3`. A policy decides whether the measured boundary count fails.

    References
    ----------
    Cites "The Python Standard Library", asyncio runners
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
        .filter(pl.col("qualified_name") == "asyncio.run")
    )
    counts = selected.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("value")
    )
    frame = facts.join(counts, on="fact_id", how="left").with_columns(pl.col("value").fill_null(0))
    finding_rows = (
        selected.select(
            "fact_id",
            "ordinal",
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
            pl.lit("`asyncio.run` creates a synchronous event-loop boundary"),
            (("asyncio run boundary", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
    )
