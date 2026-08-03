import re

import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import SyntaxFact
from ......query import FindingQuery, RuleQuery
from ......table import SyntaxRelation, Table
from ......table.relations import SyntaxTable

# Only these operators always read their operands. Libraries can overload other operators to do
# work, so the rule cannot safely call them inert.
_INERT_OPERATOR = re.compile(r"[=!<>]=|\bis\b|\bin\b|\bnot\b")
_ASSIGNMENT_OPERATOR = re.compile(r"(?:\+=|-=|\*=|/=|%=|&=|\|=|\^=|<<=|>>=)")


@rule("ALL-CONT0002")
def statement_without_effect(
    subject: Table[SyntaxFact],
    *,
    inert_kinds: tuple[str, ...] = ("name", "member", "literal", "collection", "operation"),
) -> RuleQuery[int]:
    """Count statements that compute a value and then throw it away.

    Definition
    ----------
    Report a statement whose whole content is one expression that can only produce a value, such as
    a bare name, a comparison, a literal, or a collection. Nothing happens when the line runs, so
    it is either a mistake or a line nobody needs to read. The mistake is the common case, and it
    is usually an assertion that lost its `assert`, an assignment that lost its target, or a call
    that lost its parentheses, all of which look like working code and quietly test nothing.

    What counts is the statement's whole content, which is the one node covering exactly the source
    the statement covers. Everything else beneath a statement is an operand, and an operand says
    nothing about whether the line did any work, since the `1` inside `exit(1)` is a literal in a
    statement that ends the program. Reading the widest node rather than any node underneath is
    what keeps the two apart in every language. An operation is then the one kind read further,
    since `==` compares and stops while `&`, `|`, and `>>` are how several libraries spell a
    command that runs.

    Evidence
    --------
    Each finding names the declaration, the line, and the kind of the value thrown away. The value
    is the number of statements without an effect.

    Exceptions
    ----------
    A call, an await, and a string are never counted. A call may do all its work through a side
    effect, an await always can, and a string alone is a docstring or a comment in the languages
    that allow one. An index is not counted either, because reading through an operator a type
    defines is how several libraries probe for something and how a mapping raises when it is
    missing. An operation reaching its operands through anything but a comparison, a membership
    test, or a negation is left alone, which keeps a plumbum `command & FG` and an Airflow `first
    >> second` out of the findings and costs only the rare bare `a < b`. A statement whose frontend
    states nothing beneath it is not judged. Neither is a statement whose expression the frontend
    marked in place, replacing the kind of the value with the mark, because the fact then no longer
    states what the line computed and any answer would be read off an operand, so a frontend in
    that shape reports nothing here rather than guessing.
    `inert_kinds` names the node kinds that can only produce a value, which is what a project
    extends when its language states one this list has not met.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       def check(order):
           order.total == 0
           order.items

    Good
    ~~~~
    .. code-block:: python

       def check(order):
           assert order.total == 0
           return order.items

    References
    ----------
    Generalizes Ruff B015 useless-comparison
    Generalizes Ruff B018 useless-expression
    Generalizes Clippy no_effect
    https://rust-lang.github.io/rust-clippy/master/index.html#no_effect
    Generalizes ESLint no-unused-expressions
    https://eslint.org/docs/latest/rules/no-unused-expressions
    """
    relations = SyntaxTable(table=subject)
    facts = subject.lazy(SyntaxRelation.FACTS)
    nodes = relations.nodes
    effects = nodes.filter(pl.col("kind") == "effect").select(
        "fact_id",
        pl.col("ordinal").alias("parent_ordinal"),
        pl.col("start_line").alias("effect_start_line"),
        pl.col("start_column").alias("effect_start_column"),
        pl.col("end_line").alias("effect_end_line"),
        pl.col("end_column").alias("effect_end_column"),
    )
    candidates = (
        relations.children.join(effects, on=["fact_id", "parent_ordinal"], how="inner")
        .join(
            nodes.select(
                "fact_order",
                "fact_id",
                pl.col("ordinal").alias("child_ordinal"),
                "kind",
                "path",
                "start_line",
                "start_column",
                "end_line",
                "end_column",
                "byte_start",
                "byte_length",
            ),
            on=["fact_id", "child_ordinal"],
            how="inner",
        )
        .filter(
            (pl.col("start_line") == pl.col("effect_start_line"))
            & (pl.col("start_column") == pl.col("effect_start_column"))
            & (pl.col("end_line") == pl.col("effect_end_line"))
            & (pl.col("end_column") == pl.col("effect_end_column"))
            & pl.col("kind").is_in(list(inert_kinds))
        )
    )
    reported = relations.with_text(candidates).filter(
        (pl.col("kind") != "operation")
        | (
            ~pl.col("text").str.contains(_ASSIGNMENT_OPERATOR.pattern)
            & pl.col("text").str.contains(_INERT_OPERATOR.pattern)
        )
    )
    counts = reported.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("value")
    )
    joined = facts.join(counts, on="fact_id", how="left").with_columns(
        pl.col("value").fill_null(0)
    )
    findings = FindingQuery.build(
        reported,
        pl.concat_str(
            pl.col("kind"),
            pl.lit(" expression `"),
            pl.col("text").str.strip_chars(),
            pl.lit("` is discarded"),
        ),
        (("statement without effect", pl.lit(1), Unit.COUNT),),
        finding_order=pl.col("child_ordinal"),
    )
    return RuleQuery.integer(joined, pl.col("value"), findings=findings)
