import polars as pl
from pydantic import NonNegativeInt

from ...... import rule
from ......domain.contracts import (
    FixSafety,
    Unit,
)
from ......facts import CommentFact
from ......query import CountQuery, FindingQuery, FixQuery, RuleQuery
from ......table import Table
from ......table.relations import FactRelations
from .support.relations import comment_groups, ordered


@rule("ALL-COMM0002", fix_safety=FixSafety.REVIEW)
def commented_out_code(
    subject: Table[CommentFact], *, minimum_lines: NonNegativeInt = 1
) -> CountQuery:
    """Count comment groups that are source rather than prose.

    Definition
    ----------
    Report a contiguous comment group of at least `minimum_lines` lines whose text parses as source
    in the language of the file it lives in. Commented-out code is dead weight that reads as
    intent, since it survives refactors untouched, it is never compiled or tested, and every later
    reader has to decide whether it matters. Version control already keeps the old version.

    Evidence
    --------
    Each finding records the comment range and its measured size. The value is the number of such
    groups.

    Exceptions
    ----------
    A tool directive, such as a suppression or a formatting marker, is excluded even when it
    parses.
    A documentation example inside a comment often parses too, so a project that keeps examples in
    comments should raise `minimum_lines` or exclude those paths. Prose that happens to parse, such
    as a single bare word, is why the default counts a group rather than a line.

    Examples
    --------
    Three commented lines that reconstruct a former loop return `1`. A comment reading `# retry
    twice before giving up` returns `0`, and so does a suppression directive.

    References
    ----------
    Generalizes SonarSource S125
    https://rules.sonarsource.com/python/RSPEC-S125/
    Cites "Clean Code", chapter on comments
    Cites "The Pragmatic Programmer", on commented-out code
    """
    relations = FactRelations(subject)
    selected = ordered(
        comment_groups(relations).filter(
            pl.col("parses_as_source")
            & ~pl.col("is_directive")
            & (pl.col("line_count") >= minimum_lines)
        )
    )
    frame = relations.counted(selected)
    findings = FindingQuery.build(
        selected,
        pl.concat_str(
            pl.lit("this "),
            pl.col("line_count"),
            pl.lit("-line comment group parses as source rather than prose"),
        ),
        (
            ("lines in the comment group", pl.col("line_count"), Unit.COUNT),
            ("characters in the comment group", pl.col("character_count"), Unit.COUNT),
            ("tokens in the comment group", pl.col("token_count"), Unit.COUNT),
        ),
        finding_order=pl.col("finding_order"),
    )
    repairable = selected.filter(pl.col("node.id").is_not_null())
    rewrites = repairable.select(
        "fact_id",
        pl.col("finding_order").alias("rewrite_order"),
        pl.lit("remove").alias("kind"),
        pl.lit("").alias("source"),
        pl.lit("").alias("placement"),
        pl.lit("").alias("name"),
        pl.lit("").alias("symbol_id"),
        pl.lit("").alias("symbol_name"),
        pl.lit(False).alias("references_complete"),
    )
    nodes = repairable.select(
        "fact_id",
        pl.col("finding_order").alias("rewrite_order"),
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
        findings=findings,
        fix=FixQuery.build(
            "Delete each run of commented lines that is source rather than prose.",
            rewrites=rewrites,
            nodes=nodes,
        ),
    )
