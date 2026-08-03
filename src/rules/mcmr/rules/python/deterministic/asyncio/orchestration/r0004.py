import polars as pl
from pydantic import NonNegativeInt

from ...... import rule
from ......domain.contracts import Unit
from ......facts import CallFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import CallRelation, Table


@rule("PY-ASYN0004")
def default_executor_to_thread_candidate(
    subject: Table[CallFact],
    *,
    python_minor: NonNegativeInt = 14,
) -> CountQuery:
    """Count default-executor calls that can usually use `asyncio.to_thread`.

    Definition
    ----------
    For Python 3.9 or newer, find `run_in_executor(None, callable, *args)` calls on a loop obtained
    from `asyncio.get_running_loop` or `get_event_loop`. The first `None` selects the default
    thread executor. The value is the number of candidates.

    Evidence
    --------
    Every finding identifies the call and its nearest enclosing function. The value is the number
    of default-executor calls that could become `asyncio.to_thread`.

    Exceptions
    ----------
    Keep `run_in_executor` when selecting a custom executor, retaining a specific Future contract,
    or deliberately avoiding `contextvars` propagation. `asyncio.to_thread` is for blocking work
    that should not block the event loop. It does not turn coroutine execution into threading and
    does not generally make CPU-bound Python code parallel on a GIL-enabled build. `python_minor`
    is the Python 3 minor version the project targets, and the rule reports nothing below 9 because
    `asyncio.to_thread` does not exist there.

    Examples
    --------
    `await loop.run_in_executor(None, read_file, path)` is reported and can usually become
    `await asyncio.to_thread(read_file, path)`. Passing an explicit process, interpreter, or thread
    executor is accepted.

    References
    ----------
    Cites "The Python Standard Library", `asyncio.to_thread`
    https://docs.python.org/3/library/asyncio-task.html#asyncio.to_thread
    Cites "The Python Standard Library", asyncio multithreading guidance
    https://docs.python.org/3/library/asyncio-dev.html#concurrency-and-multithreading
    """
    facts = subject.lazy(CallRelation.FACTS)
    evidence = (
        subject.lazy(CallRelation.EVIDENCE)
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("signal").sort_by("ordinal").alias("evidence"))
    )
    expressions = subject.lazy(CallRelation.EXPRESSIONS)
    arguments = (
        expressions.filter((pl.col("root_relation") == "argument") & (pl.col("depth") == 0))
        .group_by("call_id", maintain_order=True)
        .agg(
            pl.len().cast(pl.UInt64).alias("argument_count"),
            pl.col("text")
            .filter(pl.col("root_ordinal") == 0)
            .first()
            .alias("first_argument_text"),
        )
    )
    receivers = expressions.filter(
        (pl.col("root_relation") == "receiver") & (pl.col("depth") == 0)
    ).select("call_id", pl.col("text").alias("receiver_text"))
    loop_receivers = (
        subject.lazy(CallRelation.CALLS)
        .filter(
            pl.col("qualified_name").is_in(["asyncio.get_running_loop", "asyncio.get_event_loop"])
            & (pl.col("assigned_target") != "")
        )
        .select(
            "fact_id",
            pl.col("assigned_target").alias("receiver_text"),
        )
        .unique()
    )
    selected = (
        subject.lazy(CallRelation.CALLS)
        .join(facts.select("fact_id"), on="fact_id", how="inner")
        .join(arguments, on="call_id", how="inner")
        .join(receivers, on="call_id", how="inner")
        .join(loop_receivers, on=["fact_id", "receiver_text"], how="inner")
        .filter(
            pl.lit(python_minor >= 9)
            & pl.col("qualified_name").str.ends_with(".run_in_executor")
            & (pl.col("argument_count") >= 2)
            & (pl.col("first_argument_text") == "None")
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
                pl.lit(
                    "` selects the default executor and can usually become `asyncio.to_thread`"
                ),
            ),
            (("default executor to thread candidate", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
    )
