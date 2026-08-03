import polars as pl

from ..... import rule
from .....domain.contracts import Unit
from .....facts import CallFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table import CallRelation, Table


@rule("ALL-CALL0002")
def unbounded_blocking_call(
    subject: Table[CallFact],
    *,
    bounded_callables: tuple[str, ...] = (),
    bound_names: tuple[str, ...] = ("timeout", "deadline", "duration"),
) -> CountQuery:
    """Count calls that can wait forever because no bound was passed.

    Definition
    ----------
    Report a resolved call to a configured callable that names none of `bound_names` among its
    arguments. A network read, a subprocess wait, a lock acquisition, and a queue get all block
    until something else happens, and without a bound that something may never happen. The failure
    is a process that hangs rather than one that reports an error, which is why it survives review
    and testing and only appears in production.

    Evidence
    --------
    Each finding records the call range, the qualified name, and the argument names that were
    passed. The value is the number of unbounded calls.

    Exceptions
    ----------
    A deliberate wait, such as a supervisor joining its workers at shutdown or a server accepting
    connections, is legitimate and belongs outside the configured list. With no configured
    callables the rule reports nothing. A project whose bound travels in a context or a
    cancellation scope rather than an argument should name that pattern instead of this rule.
    `bounded_callables` names the calls a project considers blocking, which is why the rule reports
    nothing until somebody states them.

    Examples
    --------
    With `requests.get` configured, `requests.get(url)` returns `1` and
    `requests.get(url, timeout=5)` returns `0`.

    References
    ----------
    Cites Pylint W3101 missing-timeout
    https://pylint.readthedocs.io/en/stable/user_guide/messages/warning/missing-timeout.html
    Cites "Release It", timeouts and the integration point failure mode
    Cites "The Python Standard Library", `subprocess` documentation on the timeout argument
    https://docs.python.org/3/library/subprocess.html#subprocess.Popen.wait
    """
    facts = subject.lazy(CallRelation.FACTS)
    evidence = (
        subject.lazy(CallRelation.EVIDENCE)
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("signal").sort_by("ordinal").alias("evidence"))
    )
    calls = subject.lazy(CallRelation.CALLS).join(
        facts.select("fact_id"), on="fact_id", how="inner"
    )
    bounded = (
        subject.lazy(CallRelation.KEYWORDS)
        .filter(pl.col("name").is_in(bound_names))
        .select("call_id")
        .unique()
    )
    selected = calls.filter(pl.col("qualified_name").is_in(bounded_callables)).join(
        bounded, on="call_id", how="anti"
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
                pl.lit(
                    "` can block without any of " + ", ".join(f"`{name}`" for name in bound_names)
                ),
            ),
            (("unbounded blocking call", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
    )
