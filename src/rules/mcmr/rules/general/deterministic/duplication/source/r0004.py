import polars as pl
from pydantic import PositiveInt

from ...... import Numeric, rule
from ......domain.contracts import Unit
from ......facts import CloneGroupFact
from ......query import FindingQuery, PercentageQuery, RuleQuery
from ......table import Table
from ..relations import CloneTables


@rule("ALL-DUPL0004", policy=Numeric(maximum=3))
def duplicated_repository_share(
    subject: Table[CloneGroupFact],
    *,
    minimum_line_count: PositiveInt = 4,
) -> PercentageQuery:
    """Measure how much of the repository exists only as a copy of this block.

    Definition
    ----------
    Divide the lines this group repeats by every line the kernel read, and state the result as a
    percentage. A group of three copies covering twelve lines repeats twenty-four of them, since
    one copy is the original and the other two are what a merge would remove. A group covering
    fewer than `minimum_line_count` lines measures zero, because a run that short is shape rather
    than a paste and counting it would inflate a number people act on.

    Symilar reports the same quantity for a whole run, as duplicated lines over total lines. This
    rule reports it one group at a time, which is what makes it actionable. A repository is never
    told to reduce duplication in general, it is told that one particular block accounts for a
    share of it that nobody meant to write.

    Evidence
    --------
    The finding names where the group was first stated, how many lines it repeats, and how many
    lines the whole tree holds, and the value is the share of the tree those repeated lines
    occupy. The denominator is every line of every file the kernel read, including blank ones,
    which is the same denominator Symilar divides by.

    Exceptions
    ----------
    A clone group always names at least two nonoverlapping fragments in a nonempty repository.
    Those conditions are fact constraints rather than fallback arithmetic in this rule. The
    repository's Git ignore files decide whether generated and vendored trees are read, so a
    checked-in build directory counts unless the repository excludes it. A copy that is
    deliberate, such as a test double that mirrors the shape it stands in for, still counts here,
    because this rule measures the tree rather than judging the intent behind it.

    Examples
    --------
    Bad
    ~~~
    One eighty-line reader pasted into three modules of a two-thousand-line repository repeats one
    hundred and sixty lines, so it returns `8.0` and every fix to it has to be made three times.

    Good
    ~~~~
    The same reader lives in one module the other three import. Nothing is repeated, so the group
    disappears and the share is `0.0`. A group covering three lines also returns `0.0`, because it
    sits under the default `minimum_line_count`.

    References
    ----------
    Generalizes Pylint R0801 duplicate-code
    Cites "Clean Code", chapter 17, on duplication as the primary enemy of design
    Cites "Working Effectively with Legacy Code", chapter 20, on extraction
    """
    qualified = pl.col("line_count") >= minimum_line_count
    frame = (
        CloneTables(subject)
        .groups()
        .with_columns(
            pl.when(qualified)
            .then(pl.col("redundant_line_count") / pl.col("repository_line_count") * 100.0)
            .otherwise(pl.lit(0.0))
            .alias("share"),
            qualified.cast(pl.UInt64).alias("finding_count"),
        )
    )
    findings = FindingQuery.build(
        frame,
        pl.concat_str(
            pl.col("redundant_line_count"),
            pl.lit(" of the "),
            pl.col("repository_line_count"),
            pl.when(pl.col("repository_line_count") == 1)
            .then(pl.lit(" line"))
            .otherwise(pl.lit(" lines")),
            pl.lit(" this tree holds repeat a block of "),
            pl.col("line_count"),
            pl.when(pl.col("line_count") == 1).then(pl.lit(" line")).otherwise(pl.lit(" lines")),
            pl.lit(" that appears "),
            pl.col("copy_count"),
            pl.when(pl.col("copy_count") == 1).then(pl.lit(" time")).otherwise(pl.lit(" times")),
        ),
        (
            ("repeated lines", pl.col("redundant_line_count"), Unit.COUNT),
            ("lines in the tree", pl.col("repository_line_count"), Unit.COUNT),
            ("share of the tree", pl.col("share"), Unit.PERCENTAGE),
        ),
        predicate=qualified,
    )
    return RuleQuery.floating(
        frame,
        pl.col("share"),
        pl.col("finding_count"),
        findings=findings,
    )
