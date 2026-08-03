import polars as pl
from pydantic import NonNegativeInt

from ...... import rule
from ......domain.contracts import Unit
from ......facts import CallFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import CallRelation, Table


@rule("PY-TYPE0005")
def repeated_cast_patterns(
    subject: Table[CallFact], *, minimum_repetitions: NonNegativeInt = 3
) -> CountQuery:
    """Count casts and flag structurally repeated cast patterns.

    Definition
    ----------
    Group every call resolved to `typing.cast` or `typing_extensions.cast` by target type and
    normalized producer pattern. Subscript keys and literal values are ignored, while container
    names, attributes, and callees remain part of the pattern. A group with at least
    `minimum_repetitions` occurrences is an anti-pattern finding because repetition usually means
    the same missing type contract is being overridden at several call sites. The value counts
    casts in qualifying repeated patterns, so an isolated cast cannot fail without a finding.

    Evidence
    --------
    Each finding reports the repeated target and producer pattern, occurrence count, affected file
    count, representative location, and up to 32 exact source locations. The suggested repair
    points toward one boundary validation, a typed model or TypedDict, a type guard, a Protocol, a
    generic, or an overload. Isolated casts remain in the provider fact without becoming a
    finding. The value is the number of casts inside repeated patterns rather than the number of
    patterns.

    Exceptions
    ----------
    A cast can be appropriate at an untyped or incorrectly typed third-party boundary because
    `cast` is a static assertion and performs no runtime validation. Even boundary casts become a
    finding when the same assertion is repeated. Validate or wrap that boundary once instead.

    Examples
    --------
    Bad
    ~~~
    Three calls such as `cast(str, row["id"])`, `cast(str, row["name"])`, and
    `cast(str, row["owner"])` form the pattern `str` from `subscript row`. Parse `row` once as
    a typed record instead of asserting every field independently.

    Good
    ~~~~
    One cast around the result of an untyped extension API is counted but not flagged. Replacing
    repeated casts with `Record.model_validate(raw)` creates one runtime boundary and typed uses
    after it.

    References
    ----------
    Cites "Python typing specification", Type checker directives, `cast()`
    https://typing.python.org/en/latest/spec/directives.html#cast
    Cites "Mypy documentation", `redundant-cast`
    https://mypy.readthedocs.io/en/stable/error_code_list2.html#check-that-cast-is-not-redundant-redundant-cast
    Cites "Pyright documentation", configuration, `reportUnnecessaryCast`
    https://github.com/microsoft/pyright/blob/main/docs/configuration.md
    """
    facts = subject.lazy(CallRelation.FACTS)
    evidence = (
        subject.lazy(CallRelation.EVIDENCE)
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("signal").sort_by("ordinal").alias("evidence"))
    )
    arguments = (
        subject.lazy(CallRelation.EXPRESSIONS)
        .filter((pl.col("root_relation") == "argument") & (pl.col("depth") == 0))
        .group_by("call_id", maintain_order=True)
        .agg(
            pl.len().cast(pl.UInt64).alias("argument_count"),
            pl.col("text").filter(pl.col("root_ordinal") == 0).first().alias("cast_target"),
            pl.col("text").filter(pl.col("root_ordinal") == 1).first().alias("producer_text"),
            pl.col("qualified_name")
            .filter(pl.col("root_ordinal") == 1)
            .first()
            .alias("producer_qualified_name"),
        )
    )
    selected = (
        subject.lazy(CallRelation.CALLS)
        .join(facts.select("fact_id", "fact_order"), on="fact_id", how="inner")
        .join(arguments, on="call_id", how="inner")
        .filter(
            pl.col("qualified_name").is_in(["typing.cast", "typing_extensions.cast"])
            & (pl.col("argument_count") == 2)
        )
        .with_columns(
            pl.when(pl.col("producer_qualified_name") != "")
            .then(pl.col("producer_qualified_name"))
            .otherwise(pl.col("producer_text"))
            .alias("producer"),
            pl.when(pl.col("node_end_line") > pl.col("node_start_line"))
            .then(
                pl.concat_str(
                    pl.lit("`"),
                    pl.col("node_path"),
                    pl.lit(":"),
                    pl.col("node_start_line"),
                    pl.lit("-"),
                    pl.col("node_end_line"),
                    pl.lit("`"),
                )
            )
            .otherwise(
                pl.concat_str(
                    pl.lit("`"),
                    pl.col("node_path"),
                    pl.lit(":"),
                    pl.col("node_start_line"),
                    pl.lit("`"),
                )
            )
            .alias("location"),
        )
    )
    repeated = (
        selected.group_by("cast_target", "producer", maintain_order=True)
        .agg(
            pl.len().cast(pl.UInt64).alias("group_count"),
            pl.col("path").n_unique().cast(pl.UInt64).alias("file_count"),
            pl.col("location")
            .sort_by(["fact_order", "ordinal"])
            .head(32)
            .str.join(", ")
            .alias("locations"),
            pl.col("fact_id").sort_by(["fact_order", "ordinal"]).first().alias("fact_id"),
            pl.col("node_path").sort_by(["fact_order", "ordinal"]).first().alias("path"),
            pl.col("node_start_line")
            .sort_by(["fact_order", "ordinal"])
            .first()
            .alias("start_line"),
            pl.col("node_start_column")
            .sort_by(["fact_order", "ordinal"])
            .first()
            .alias("start_column"),
            pl.col("node_end_line").sort_by(["fact_order", "ordinal"]).first().alias("end_line"),
            pl.col("node_end_column")
            .sort_by(["fact_order", "ordinal"])
            .first()
            .alias("end_column"),
        )
        .filter(pl.col("group_count") >= minimum_repetitions)
        .sort("cast_target", "producer")
        .with_row_index("finding_order")
    )
    counts = repeated.group_by("fact_id", maintain_order=True).agg(
        pl.col("group_count").sum().cast(pl.UInt64).alias("value")
    )
    frame = facts.join(counts, on="fact_id", how="left").with_columns(pl.col("value").fill_null(0))
    finding_rows = repeated.join(evidence, on="fact_id", how="left").with_columns(
        pl.col("evidence").fill_null(pl.lit([], dtype=pl.List(pl.String)))
    )
    value = pl.col("value")
    return RuleQuery.integer(
        frame,
        value,
        findings=FindingQuery.build(
            finding_rows,
            pl.concat_str(
                pl.lit("cast to `"),
                pl.col("cast_target"),
                pl.lit("` from `"),
                pl.col("producer"),
                pl.lit("` repeats "),
                pl.col("group_count"),
                pl.lit(" times across "),
                pl.col("file_count"),
                pl.lit(" files at "),
                pl.col("locations"),
            ),
            (
                ("casts in this pattern", pl.col("group_count"), Unit.COUNT),
                ("files holding this pattern", pl.col("file_count"), Unit.COUNT),
            ),
            finding_order=pl.col("finding_order"),
            evidence=pl.col("evidence"),
        ),
    )
