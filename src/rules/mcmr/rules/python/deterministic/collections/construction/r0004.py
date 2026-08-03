import polars as pl

from ...... import rule
from ......domain.contracts import (
    FixSafety,
    Unit,
)
from ......facts import CallFact
from ......query import CountQuery, FindingQuery, FixQuery, RuleQuery
from ......table import CallRelation, Table


@rule("PY-COLL0004", fix_safety=FixSafety.REVIEW)
def explicit_tuple_construction(subject: Table[CallFact]) -> CountQuery:
    """Count explicit immutable collection construction in project code.

    Definition
    ----------
    Report every unshadowed call to the builtin `tuple` or `frozenset` constructor. This project's
    internal collection policy uses lists and sets unless immutable identity is a proved domain or
    public contract. A constructor call is the exact place that concrete representation enters.

    Evidence
    --------
    The value is the number of immutable collection constructor calls. A review fix converts an
    empty tuple or tuple built from a literal sequence to the corresponding list. Other calls stay
    report-only because changing hashability, ordering, or a public return type needs review.

    Exceptions
    ----------
    A source file that binds either builtin name is conservatively excluded because the call may
    target project code. Keep immutable identity where the value is a dictionary key, crosses a
    stable public boundary, or is required by another API, and exclude that exact location.

    Examples
    --------
    Bad
    ~~~
    `items = tuple(source)` and `names = frozenset(values)` force internal data into immutable
    concrete containers without a stated contract.

    Good
    ~~~~
    `items = list(source)` and `names = set(values)` retain the general project representation. A
    fixed heterogeneous tuple such as `(x, y)` remains a record expression and is not a
    constructor.

    References
    ----------
    Cites "Fluent Python", chapter 2, An Array of Sequences
    Cites "The Python Language Reference", list displays
    https://docs.python.org/3.14/reference/expressions.html#list-displays
    Cites "Pydantic documentation", standard library types, tuples
    https://docs.pydantic.dev/latest/api/standard_library_types/#tuples
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
            pl.col("text")
            .filter(pl.col("root_ordinal") == 0)
            .first()
            .alias("first_argument_text"),
            pl.col("literal_kind")
            .filter(pl.col("root_ordinal") == 0)
            .first()
            .alias("first_argument_literal_kind"),
        )
    )
    keyword_calls = subject.lazy(CallRelation.KEYWORDS).select("call_id").unique()
    calls = (
        subject.lazy(CallRelation.CALLS)
        .join(facts.select("fact_id"), on="fact_id", how="inner")
        .join(arguments, on="call_id", how="left")
        .with_columns(
            pl.col("argument_count").fill_null(0),
            pl.col("first_argument_text").fill_null(""),
            pl.col("first_argument_literal_kind").fill_null("none"),
        )
        .join(keyword_calls, on="call_id", how="anti")
    )
    literal_sequence = (
        (pl.col("argument_count") == 1)
        & (pl.col("first_argument_literal_kind") == "sequence")
        & pl.any_horizontal(
            pl.col("first_argument_text").str.strip_chars_start().str.starts_with("["),
            pl.col("first_argument_text").str.strip_chars_start().str.starts_with("("),
        )
    )
    selected = calls.filter(
        pl.col("qualified_name").is_in(["builtins.tuple", "builtins.frozenset"])
        & ~pl.col("is_shadowed")
        & ~pl.col("has_starred_arguments")
    )
    counts = selected.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("value")
    )
    frame = facts.join(counts, on="fact_id", how="left").with_columns(pl.col("value").fill_null(0))
    finding_rows = (
        selected.select(
            "fact_id",
            "ordinal",
            "node_text",
            "argument_count",
            "first_argument_literal_kind",
            pl.col("node_path").alias("path"),
            pl.col("node_start_line").alias("start_line"),
            pl.col("node_start_column").alias("start_column"),
            pl.col("node_end_line").alias("end_line"),
            pl.col("node_end_column").alias("end_column"),
        )
        .join(evidence, on="fact_id", how="left")
        .with_columns(pl.col("evidence").fill_null(pl.lit([], dtype=pl.List(pl.String))))
    )
    repairable = selected.filter(
        (pl.col("qualified_name") == "builtins.tuple")
        & ((pl.col("argument_count") == 0) | literal_sequence)
    )
    rewrites = repairable.select(
        "fact_id",
        pl.col("ordinal").alias("rewrite_order"),
        pl.lit("replace").alias("kind"),
        pl.when(pl.col("argument_count") == 0)
        .then(pl.lit("[]"))
        .otherwise(
            pl.when(pl.col("first_argument_text").str.strip_chars_start().str.starts_with("["))
            .then(pl.col("first_argument_text"))
            .otherwise(
                pl.concat_str(
                    pl.lit("["),
                    pl.col("first_argument_text").str.strip_prefix("(").str.strip_suffix(")"),
                    pl.lit("]"),
                )
            )
        )
        .alias("source"),
        pl.lit("").alias("placement"),
        pl.lit("").alias("name"),
        pl.lit("").alias("symbol_id"),
        pl.lit("").alias("symbol_name"),
        pl.lit(False).alias("references_complete"),
    )
    nodes = repairable.select(
        "fact_id",
        pl.col("ordinal").alias("rewrite_order"),
        pl.lit("target").alias("role"),
        pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
        pl.col("node_id").alias("id"),
        pl.col("node_path").alias("path"),
        pl.col("node_start_line").alias("start_line"),
        pl.col("node_start_column").alias("start_column"),
        pl.col("node_end_line").alias("end_line"),
        pl.col("node_end_column").alias("end_column"),
        pl.col("node_kind").alias("kind"),
        pl.col("node_text").alias("text"),
    )
    value = pl.col("value")
    return RuleQuery.integer(
        frame,
        value,
        findings=FindingQuery.build(
            finding_rows,
            pl.concat_str(
                pl.lit("`"),
                pl.when(pl.col("node_text") != "")
                .then(pl.col("node_text"))
                .otherwise(pl.lit("immutable collection constructor")),
                pl.lit("` constructs an immutable collection from "),
                pl.when(pl.col("argument_count") == 0)
                .then(pl.lit("no input"))
                .otherwise(
                    pl.when(pl.col("first_argument_literal_kind") == "none")
                    .then(pl.lit("an input expression"))
                    .otherwise(pl.col("first_argument_literal_kind"))
                ),
            ),
            (("explicit immutable collection construction", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
        fix=FixQuery.build(
            "Use the project's ordinary mutable collection representation.",
            rewrites=rewrites,
            nodes=nodes,
        ),
    )
