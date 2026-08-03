import re

import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import SyntaxFact
from ......query import FindingQuery, RuleQuery
from ......table import SyntaxRelation, Table
from ......table.relations import SyntaxTable

# Match the alternative clause spellings shared by Python and brace languages without teaching
# the rule a complete grammar.
_ALTERNATIVE = re.compile(r"\}?\s*(?:else|elif|elsif)\b")

# The first word of a statement, with the trailing bang a Rust macro carries, because `panic!` and
# `return` leave a block the same way and only the spelling differs.
_LEADING_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*!?")


@rule("ALL-CONT0001")
def superfluous_else_after_jump(
    subject: Table[SyntaxFact],
    *,
    jumps: tuple[str, ...] = ("return", "raise", "throw", "break", "continue", "panic!"),
) -> RuleQuery[int]:
    """Count else clauses a jump in the block above them already made unnecessary.

    Definition
    ----------
    Report a branch whose last statement before the alternative leaves the block for good, through
    a return, a raise, a throw, a break, or a continue. Once that statement runs nothing else in
    the block runs, so the else adds no information a reader did not already have. What it does add
    is a level of indentation, and every level costs the reader one more condition to hold in mind
    while reading the rest of the work.

    The alternative is read at the branch's own indentation, which is `else` in Python and
    `} else {` in C, C++, Rust, and TypeScript, and the jump is read from the first word of the
    statement before it. Both readings are language neutral, so one rule answers for every frontend
    that fills a tree, and a frontend that states no statements inside a branch still gets an
    answer from the source the branch carries.

    Evidence
    --------
    Each finding names the declaration, the branch, and the line its alternative opens on. The
    value is the number of alternatives a jump already made unnecessary.

    Exceptions
    ----------
    A branch whose first block ends in ordinary work keeps its else, because there the else is the
    only thing saying the two blocks exclude each other. An else belonging to a nested branch is
    charged to that branch and never to the one holding it, which is what reading the indentation
    buys. A language whose block yields a value instead of jumping, such as a Rust `if` written as
    an expression, states no keyword to find and is left alone. A statement that closes its block
    on a brace or a bare continuation line, rather than on the word that jumps, is left alone too,
    which under-reports and never over-reports. A branch carrying no span at all is not judged,
    since nothing then locates the alternative.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       if not values:
           return 0
       else:
           return sum(values)

    Good
    ~~~~
    .. code-block:: python

       if not values:
           return 0
       return sum(values)

    The same shape in Rust is `if values.is_empty() { return 0; } else { ... }`, and the same
    repair drops the `else` and dedents everything it held.

    References
    ----------
    Generalizes Ruff RET505 superfluous-else-return
    Generalizes Ruff RET506 superfluous-else-raise
    Generalizes Ruff RET507 superfluous-else-continue
    Generalizes Ruff RET508 superfluous-else-break
    Cites Pylint R1705 no-else-return
    https://pylint.readthedocs.io/en/latest/user_guide/messages/refactor/no-else-return.html
    Cites "Go Code Review Comments", indent error flow
    https://go.dev/wiki/CodeReviewComments#indent-error-flow
    """
    relations = SyntaxTable(table=subject)
    facts = subject.lazy(SyntaxRelation.FACTS)
    nodes = relations.nodes
    branches = relations.with_text(nodes.filter(pl.col("kind") == "branch")).select(
        "fact_id",
        pl.col("ordinal").alias("branch_ordinal"),
        "path",
        "start_line",
        "start_column",
        "end_line",
        "end_column",
        pl.col("start_line").alias("branch_start_line"),
        pl.col("start_column").alias("branch_column"),
        pl.col("text").str.split("\n").alias("lines"),
    )
    lines = (
        branches.with_columns(pl.int_ranges(0, pl.col("lines").list.len()).alias("offset"))
        .explode("lines", "offset", empty_as_null=True)
        .with_columns(
            (
                pl.col("lines").str.len_chars()
                - pl.col("lines").str.strip_chars_start().str.len_chars()
            ).alias("indent"),
            pl.col("lines").str.strip_chars().alias("stripped"),
        )
    )
    alternatives = (
        lines.filter(
            (pl.col("offset") > 0)
            & (pl.col("indent") == pl.col("branch_column"))
            & pl.col("stripped").str.contains(_ALTERNATIVE.pattern)
        )
        .group_by("fact_id", "branch_ordinal", maintain_order=True)
        .agg(
            pl.col("offset").first().alias("alternative_offset"),
            pl.col("branch_start_line").first(),
            pl.col("path").first(),
            pl.col("start_line").first(),
            pl.col("start_column").first(),
            pl.col("end_line").first(),
            pl.col("end_column").first(),
        )
        .with_columns(
            (pl.col("branch_start_line") + pl.col("alternative_offset")).alias("alternative_line")
        )
    )
    direct_candidates = (
        relations.children.select(
            "fact_id",
            pl.col("parent_ordinal").alias("branch_ordinal"),
            "child_order",
            "child_ordinal",
        )
        .join(alternatives, on=["fact_id", "branch_ordinal"], how="inner")
        .join(
            nodes.select(
                "fact_order",
                "fact_id",
                pl.col("ordinal").alias("child_ordinal"),
                "end_line",
                "byte_start",
                "byte_length",
            ),
            on=["fact_id", "child_ordinal"],
            how="inner",
        )
        .filter(pl.col("end_line") < pl.col("alternative_line"))
    )
    direct = (
        relations.with_text(direct_candidates)
        .sort("fact_id", "branch_ordinal", "end_line", "child_order")
        .group_by("fact_id", "branch_ordinal", maintain_order=True)
        .agg(pl.col("text").last().str.strip_chars_start().alias("direct_closing"))
    )
    fallback = (
        lines.join(alternatives, on=["fact_id", "branch_ordinal"], how="inner")
        .filter((pl.col("offset") >= 1) & (pl.col("offset") < pl.col("alternative_offset")))
        .with_columns(
            pl.col("indent")
            .filter(pl.col("offset") == 1)
            .first()
            .over("fact_id", "branch_ordinal")
            .alias("opened")
        )
        .filter(pl.col("indent") == pl.col("opened"))
        .sort("fact_id", "branch_ordinal", "offset")
        .group_by("fact_id", "branch_ordinal", maintain_order=True)
        .agg(pl.col("lines").last().str.strip_chars_start().alias("fallback_closing"))
    )
    reported = (
        alternatives.join(direct, on=["fact_id", "branch_ordinal"], how="left")
        .join(fallback, on=["fact_id", "branch_ordinal"], how="left")
        .with_columns(
            pl.coalesce("direct_closing", "fallback_closing")
            .str.extract(_LEADING_WORD.pattern, 0)
            .alias("jump")
        )
        .filter(pl.col("jump").is_in(list(jumps)))
    )
    counts = reported.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("value")
    )
    joined = facts.join(counts, on="fact_id", how="left").with_columns(
        pl.col("value").fill_null(0)
    )
    location = (
        pl.when(pl.col("end_line") > pl.col("start_line"))
        .then(
            pl.concat_str(
                pl.col("path"),
                pl.lit(":"),
                pl.col("start_line"),
                pl.lit("-"),
                pl.col("end_line"),
            )
        )
        .otherwise(pl.concat_str(pl.col("path"), pl.lit(":"), pl.col("start_line")))
    )
    findings = FindingQuery.build(
        reported,
        pl.concat_str(
            pl.lit("branch at `"),
            location,
            pl.lit("` keeps an alternative after its first arm jumps"),
        ),
        (("superfluous else after jump", pl.lit(1), Unit.COUNT),),
        finding_order=pl.col("branch_ordinal"),
    )
    return RuleQuery.integer(joined, pl.col("value"), findings=findings)
