from collections.abc import Sequence

import polars as pl
from pydantic import PositiveInt

from ...... import Numeric, rule
from ......domain.contracts import Unit
from ......facts import CommentFact
from ......query import FindingQuery, PercentageQuery, RuleQuery
from ......table import Table
from ......table.relations import FactRelations
from ..relations import comment_groups, four_significant_digits


@rule("ALL-COMM0001", policy=Numeric(maximum=20))
def comment_length(
    subject: Table[CommentFact],
    *,
    measure: str = "tokens",
    normalization_max: PositiveInt = 200,
    notice_markers: Sequence[str] = (
        "spdx-license-identifier",
        "copyright",
        "licensed under",
        "all rights reserved",
    ),
) -> PercentageQuery:
    """Normalize the longest contiguous implementation comment.

    Definition
    ----------
    Consecutive ordinary comment lines form one group, `measure` chooses what a group's size is
    counted in, and the largest group in the file that is not a legal notice is the one measured.
    Documentation comments belong to the prose rules because their job is to explain a public
    contract rather than an implementation decision. That raw size is divided by
    `normalization_max` and stated as a percentage, so a group at or past the normalization maximum
    reads as one hundred and everything shorter scales beneath it.

    A licence is left out because it is not a comment about this code. It is the same words in
    every file of the project, put there by policy, and the fifteen-line notice one library opens
    all of its two hundred and six files with made this rule fail every one of them, which tells a
    reader nothing at all. `notice_markers` names what a notice opens with, so a project spelling
    one differently configures it rather than turning the rule off.

    The normalization is what makes the number comparable. A raw token count means nothing across
    two repositories with different comment habits, and a share of an agreed ceiling means the same
    thing in both. The rule states the share and a project policy decides which share is too much,
    since a protocol citation and a restated line of code are the same length and worth very
    different things.

    Evidence
    --------
    The finding names the file and range of the largest ordinary comment group it measured together
    with its raw size in the selected measure. The value is that size as a percentage of
    `normalization_max`, clipped at one hundred.

    Exceptions
    ----------
    A file with no ordinary comment measures zero rather than being skipped, which keeps the value
    comparable across a repository, and so does a file holding only documentation or its licence.
    Nothing here judges whether a long implementation comment is worth its length, so a rationale
    and a safety note measure exactly as long as they are. The contextual comment rules say whether
    they earn it.

    Examples
    --------
    A forty-token group under the default two-hundred-token normalization maximum returns `20`. A
    two-hundred-and-fifty-token group returns `100`, since the value is clipped rather than allowed
    past the ceiling. A file whose longest run of comment lines is a single line returns close to
    zero, and one opening with a fifteen-line Apache notice and saying nothing else returns `0`.

    References
    ----------
    Cites "Clean Code", chapter 4
    Cites "A Philosophy of Software Design", chapters 12 through 15
    """
    relations = FactRelations(subject)
    match measure:
        case "tokens":
            size = pl.col("token_count")
        case "characters":
            size = pl.col("character_count")
        case "lines":
            size = pl.col("line_count")
        case _:
            raise ValueError(f"Unsupported comment measure {measure!r}")
    legal_notice = pl.lit(False)
    written = pl.col("node.text").fill_null("").str.to_lowercase()
    for marker in notice_markers:
        legal_notice |= written.str.contains(marker, literal=True)
    selected = (
        comment_groups(relations)
        .filter(~pl.col("is_documentation") & ~legal_notice)
        .with_columns(size.cast(pl.UInt64).alias("largest"))
        .sort(
            ["fact_order", "largest", "ordinal"],
            descending=[False, True, False],
        )
        .unique("fact_id", keep="first", maintain_order=True)
        .with_columns(
            (pl.col("largest") / normalization_max * 100.0).clip(upper_bound=100.0).alias("share")
        )
    )
    frame = (
        relations.facts()
        .join(selected.select("fact_id", "share"), on="fact_id", how="left")
        .with_columns(
            pl.col("share").is_not_null().cast(pl.UInt64).alias("finding_count"),
            pl.col("share").fill_null(0.0),
        )
    )
    findings = FindingQuery.build(
        selected,
        pl.concat_str(
            pl.lit("the largest comment group spans "),
            pl.col("largest"),
            pl.when(pl.col("largest") == 1)
            .then(pl.lit(f" {measure[:-1]}"))
            .otherwise(pl.lit(f" {measure}")),
            pl.lit(", which is "),
            four_significant_digits(pl.col("share")),
            pl.lit(
                f" percent of the {normalization_max} {measure} used as the normalization maximum"
            ),
        ),
        (
            (f"{measure} in the comment group", pl.col("largest"), Unit.COUNT),
            (f"{measure} at the normalization maximum", pl.lit(normalization_max), Unit.COUNT),
            ("normalized comment length", pl.col("share"), Unit.PERCENTAGE),
        ),
    )
    return RuleQuery.floating(
        frame,
        pl.col("share"),
        pl.col("finding_count"),
        findings=findings,
    )
