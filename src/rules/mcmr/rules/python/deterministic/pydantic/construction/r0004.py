import polars as pl

from ...... import rule
from ......domain.contracts import (
    FixSafety,
    Unit,
)
from ......facts import CallFact
from ......query import CountQuery, FindingQuery, FixQuery, RuleQuery
from ......table import CallRelation, Table


@rule("PY-PYDA0004", fix_safety=FixSafety.SAFE)
def redundant_model_validate(subject: Table[CallFact]) -> CountQuery:
    """Find `model_validate` calls that already spell out ordinary constructor fields.

    Definition
    ----------
    Report `Model.model_validate` only when its sole argument is a dictionary literal or a
    keyword-only `dict` call with nonempty identifier keys and no validation options. In this
    shape the code already knows every field and `Model(field=value)` states that intent more
    directly. Keep `model_validate` at boundaries that receive an existing mapping, decoded
    document, ORM object, plugin payload, or caller-selected validation options.

    Evidence
    --------
    Each finding identifies the call and every explicit input key. The rule does not infer model
    schemas, aliases, or data produced at runtime. The value is the number of `model_validate`
    calls carrying one literal mapping.

    Exceptions
    ----------
    Mapping variables, dictionary unpacking, non-identifier aliases, `from_attributes`, strictness,
    context, and other validation options are excluded. Tests are excluded because literal
    mappings there often exercise decoded configuration and invalid input boundaries. A thin
    `from_table` method may reasonably call `cls.model_validate(table)` because the mapping itself
    is the boundary.

    Examples
    --------
    Bad
    ~~~
    `User.model_validate({"name": name, "age": age})` repeats an ordinary constructor shape.

    Good
    ~~~~
    `User(name=name, age=age)` constructs explicit application values. `User.model_validate(row)`
    validates an existing external mapping and remains appropriate.

    References
    ----------
    Cites "Pydantic documentation", models and model validation methods
    https://pydantic.dev/docs/validation/latest/concepts/models/
    Cites "Pydantic documentation", aliases and mapping validation
    https://pydantic.dev/docs/validation/latest/concepts/alias/
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
            pl.col("expression_id")
            .filter(pl.col("root_ordinal") == 0)
            .first()
            .alias("first_argument_id"),
            pl.col("literal_kind")
            .filter(pl.col("root_ordinal") == 0)
            .first()
            .alias("first_argument_literal_kind"),
        )
    )
    entries = (
        subject.lazy(CallRelation.MAPPING_ENTRIES)
        .join(
            expressions.select(
                pl.col("expression_id").alias("value_expression_id"),
                pl.col("text").alias("value_text"),
            ),
            on="value_expression_id",
            how="inner",
        )
        .with_columns(
            pl.concat_str(pl.lit("`"), pl.col("key"), pl.lit("`")).alias("field_name"),
            pl.concat_str(pl.col("key"), pl.lit("="), pl.col("value_text")).alias(
                "constructor_keyword"
            ),
        )
        .group_by("expression_id", maintain_order=True)
        .agg(
            pl.col("field_name").sort_by("ordinal").str.join(", ").alias("fields"),
            pl.col("constructor_keyword")
            .sort_by("ordinal")
            .str.join(", ")
            .alias("constructor_keywords"),
        )
    )
    receivers = expressions.filter(
        (pl.col("root_relation") == "receiver") & (pl.col("depth") == 0)
    ).select("call_id", pl.col("text").alias("receiver_text"))
    keyword_calls = subject.lazy(CallRelation.KEYWORDS).select("call_id").unique()
    selected = (
        subject.lazy(CallRelation.CALLS)
        .join(facts.select("fact_id", "is_test"), on="fact_id", how="inner")
        .join(arguments, on="call_id", how="inner")
        .join(entries, left_on="first_argument_id", right_on="expression_id", how="left")
        .with_columns(
            pl.col("fields").fill_null(""),
            pl.col("constructor_keywords").fill_null(""),
        )
        .join(keyword_calls, on="call_id", how="anti")
        .filter(
            ~pl.col("is_test")
            & pl.col("qualified_name").str.ends_with(".model_validate")
            & (pl.col("argument_count") == 1)
            & (pl.col("first_argument_literal_kind") == "mapping")
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
            "fields",
            pl.col("node_path").alias("path"),
            pl.col("node_start_line").alias("start_line"),
            pl.col("node_start_column").alias("start_column"),
            pl.col("node_end_line").alias("end_line"),
            pl.col("node_end_column").alias("end_column"),
        )
        .join(evidence, on="fact_id", how="left")
        .with_columns(pl.col("evidence").fill_null(pl.lit([], dtype=pl.List(pl.String))))
    )
    repairable = selected.join(receivers, on="call_id", how="inner")
    rewrites = repairable.select(
        "fact_id",
        pl.col("ordinal").alias("rewrite_order"),
        pl.lit("replace").alias("kind"),
        pl.concat_str(
            pl.col("receiver_text"),
            pl.lit("("),
            pl.col("constructor_keywords"),
            pl.lit(")"),
        ).alias("source"),
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
                pl.col("qualified_name"),
                pl.lit("` validates an explicit mapping with fields "),
                pl.col("fields"),
            ),
            (("redundant model validate", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
        fix=FixQuery.build(
            "State the known fields through the model constructor itself.",
            rewrites=rewrites,
            nodes=nodes,
        ),
    )
