import polars as pl

from ..... import rule
from .....domain.contracts import Unit
from .....facts import CallFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table import CallRelation, Table


@rule("ALL-CALL0001")
def unchecked_result_call(
    subject: Table[CallFact],
    *,
    checked_callables: tuple[str, ...] = (),
    checked_prefixes: tuple[str, ...] = (),
) -> CountQuery:
    """Count calls whose result reports failure and is discarded anyway.

    Definition
    ----------
    Report a resolved call to a configured callable, or to any callable under a configured prefix,
    whose returned value is discarded. These are the calls that report failure through their result
    rather than by raising, so discarding the result discards the only failure signal there is. The
    project names the callables because the contract lives in the library rather than in the
    syntax. A CUDA runtime entry point, a Go function returning an error, a Rust `#[must_use]`
    result, and a status-returning C API all have this shape.

    Evidence
    --------
    Each finding records the call range and the qualified name. The value is the number of
    discarded results.

    Exceptions
    ----------
    A call whose value is assigned, returned, or passed onward is not counted, even when the
    receiving code ignores it later, because that is a separate question about the receiver. With
    no configured names the rule reports nothing, since guessing which results matter would produce
    findings a project never asked for. `checked_callables` names the exact callables whose result
    reports failure and `checked_prefixes` names the families of them, so a project states its own
    contract rather than inheriting a guess.

    Examples
    --------
    With `cuda*` configured, a bare `cudaMalloc(&pointer, bytes);` returns `1` while
    `status = cudaMalloc(&pointer, bytes);` returns `0`.

    References
    ----------
    Cites "CUDA C++ Best Practices Guide", error handling
    https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html#error-handling
    Generalizes clang-tidy bugprone-unused-return-value
    https://clang.llvm.org/extra/clang-tidy/checks/bugprone/unused-return-value.html
    Cites "The Rust Reference", `#[must_use]` attribute
    https://doc.rust-lang.org/reference/attributes/diagnostics.html#the-must_use-attribute
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
    prefix_match = (
        pl.any_horizontal(
            [pl.col("qualified_name").str.starts_with(prefix) for prefix in checked_prefixes]
        )
        if checked_prefixes
        else pl.lit(False)
    )
    selected = calls.filter(
        pl.col("result_is_discarded")
        & (pl.col("qualified_name").is_in(checked_callables) | prefix_match)
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
                pl.lit("` discards the result that reports failure"),
            ),
            (("unchecked result call", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
    )
