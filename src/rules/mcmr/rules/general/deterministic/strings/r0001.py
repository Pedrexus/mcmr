import polars as pl
from pydantic import NonNegativeInt

from ..... import rule
from .....domain.contracts import (
    FixSafety,
    Unit,
)
from .....facts import StringExpressionFact
from .....query import CountQuery, FindingQuery, FixQuery, RuleQuery
from .....table import Table


@rule("ALL-STRI0001", fix_safety=FixSafety.SAFE)
def fragmented_multiline_literal(
    subject: Table[StringExpressionFact], *, minimum_fragments: NonNegativeInt = 2
) -> CountQuery:
    """Count multiline values assembled from adjacent literal fragments.

    Definition
    ----------
    Inspect folded string constants whose runtime value contains at least one newline. Count the
    lexical string tokens that Python implicitly concatenates and report the expression when the
    count reaches `minimum_fragments`. A triple-quoted or escaped single literal is one token and
    is not reported. Adjacent fragments used only to wrap one runtime line are also excluded.

    Evidence
    --------
    Every finding gives the complete expression range and its literal-fragment count. The result
    value is the number of reported expressions.

    Exceptions
    ----------
    Keep fragments when exact indentation, escaping, translation extraction, generated text, or
    a deliberate trailing-newline policy is clearer than one literal. The safe fix chooses the
    triple quote absent from the value and leaves values containing backslashes or both quote forms
    for review. Ruff ISC003 separately prefers implicit adjacency over an explicit `+` between
    literals.

    Examples
    --------
    `("first line\\n" "second line\\n")` is reported as a two-fragment multiline value. One
    triple-quoted literal containing both lines is accepted. `("one long " "runtime line")` is
    accepted because changing it to a multiline literal would change its value.

    References
    ----------
    Cites "The Python Language Reference", string literal concatenation
    https://docs.python.org/3/reference/lexical_analysis.html#string-literal-concatenation
    Generalizes Ruff ISC003 explicit-string-concatenation
    https://docs.astral.sh/ruff/rules/explicit-string-concatenation/
    """
    relations = subject
    facts = relations.facts()
    expressions = relations.records("expressions")
    is_fragmented = (
        (pl.col("kind") == "literal")
        & pl.col("runtime_value").str.contains("\n", literal=True)
        & (pl.col("literal_fragment_count") >= minimum_fragments)
    )
    selected = expressions.filter(is_fragmented & ~pl.col("wraps_single_runtime_line"))
    frame = relations.counted(selected)
    finding_rows = selected.join(
        facts.select("fact_id", "evidence"), on="fact_id", how="inner"
    ).with_columns(
        pl.col("node.span.path").alias("path"),
        pl.col("node.span.start_line").alias("start_line"),
        pl.col("node.span.start_column").alias("start_column"),
        pl.col("node.span.end_line").alias("end_line"),
        pl.col("node.span.end_column").alias("end_column"),
    )
    has_double = pl.col("runtime_value").str.contains('"""', literal=True)
    has_single = pl.col("runtime_value").str.contains("'''", literal=True)
    has_backslash = pl.col("runtime_value").str.contains("\\", literal=True)
    fixable = expressions.join(
        facts.select("fact_id", "language"), on="fact_id", how="inner"
    ).filter(
        is_fragmented
        & (pl.col("language") == "python")
        & ~has_backslash
        & ~(has_double & has_single)
    )
    encoded = (
        pl.when(has_double)
        .then(pl.concat_str(pl.lit("'''"), pl.col("runtime_value"), pl.lit("'''")))
        .otherwise(pl.concat_str(pl.lit('"""'), pl.col("runtime_value"), pl.lit('"""')))
    )
    rewrites = fixable.select(
        "fact_id",
        pl.col("ordinal").cast(pl.UInt64).alias("rewrite_order"),
        pl.lit("replace").alias("kind"),
        encoded.alias("source"),
        pl.lit("").alias("placement"),
        pl.lit("").alias("name"),
        pl.lit("").alias("symbol_id"),
        pl.lit("").alias("symbol_name"),
        pl.lit(False).alias("references_complete"),
    )
    nodes = fixable.select(
        "fact_id",
        pl.col("ordinal").cast(pl.UInt64).alias("rewrite_order"),
        pl.lit("target").alias("role"),
        pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
        pl.col("node.id").alias("id"),
        pl.col("node.span.path").alias("path"),
        pl.col("node.span.start_line").cast(pl.UInt64).alias("start_line"),
        pl.col("node.span.start_column").cast(pl.UInt64).alias("start_column"),
        pl.col("node.span.end_line").cast(pl.UInt64).alias("end_line"),
        pl.col("node.span.end_column").cast(pl.UInt64).alias("end_column"),
        pl.col("node.kind").alias("kind"),
        pl.col("node.text").alias("text"),
    )
    return RuleQuery.integer(
        frame,
        pl.col("value"),
        findings=FindingQuery.build(
            finding_rows,
            pl.concat_str(
                pl.lit("Multiline value is split across "),
                pl.col("literal_fragment_count"),
                pl.lit(" adjacent literal fragments"),
            ),
            (("fragmented multiline literal", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
        fix=FixQuery.build(
            "State each fragmented value once as one multiline literal.",
            rewrites=rewrites,
            nodes=nodes,
        ),
    )
