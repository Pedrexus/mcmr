import polars as pl
from pydantic import NonNegativeInt

from ...... import Numeric, rule
from ......domain.contracts import Unit
from ......facts import ProseSegmentFact
from ......query import FindingQuery, PercentageQuery, RuleQuery
from ......table import Table
from ..prose_relations import ProseRelations


@rule("ALL-WRIT0005", policy=Numeric(maximum=30))
def sentence_opener_concentration(
    subject: Table[ProseSegmentFact],
    *,
    minimum_sentences: NonNegativeInt = 6,
    ignored_openers: tuple[str, ...] = ("a", "i"),
) -> PercentageQuery:
    """Measure the share of sentences using one dominant opening word.

    Definition
    ----------
    Take the first word of every sentence in each prose section, fold its case, and drop the words
    listed in `ignored_openers`. In each section holding at least `minimum_sentences` of the
    remaining openers, divide the count of the most frequent opener by the number of openers and
    state it as a percentage. Return the highest value any section reaches.

    An opener repeated across most sentences is a rhythm a reader hears, and it is usually a sign
    that each sentence was started rather than continued. Like the length measures this reports a
    share and claims nothing about who wrote the text.

    Evidence
    --------
    The finding names the dominant opener, how many sentences it opens, how many openers the
    section holds, and the resulting percentage. Ties are broken alphabetically so two runs over
    the same text report the same word. The value is the highest section concentration in the
    document, as a percentage of its eligible sentences.

    Exceptions
    ----------
    A section holding fewer than `minimum_sentences` eligible openers is skipped rather than
    measured. `ignored_openers` drops the words whose repetition means nothing, which is `a` and
    `i` by default, and a project working in another language states its own. Repetition can be
    deliberate anaphora or required terminology, and first-person prose repeats its subject by
    nature, so the value is evidence a person reads rather than a verdict.

    Examples
    --------
    Where `This` opens three of six eligible sentences, the section returns `50`. Six sentences
    opening with six distinct words return about `16.67`. A section holding five eligible openers
    is skipped under the default `minimum_sentences`, and a document of only such sections returns
    `0`.

    References
    ----------
    Cites "Vale AI Tells", experimental SentenceStartRepetition rule
    https://github.com/tbhb/vale-ai-tells/blob/main/EXPERIMENTAL.md
    Cites "Do LLMs Write Like Humans"
    https://arxiv.org/abs/2410.16107
    """
    relations = ProseRelations(subject)
    sections = relations.opener_concentrations(minimum_sentences, ignored_openers)
    greatest = sections.group_by("fact_id", maintain_order=True).agg(
        pl.col("share").max().alias("value")
    )
    frame = (
        relations.facts()
        .join(greatest, on="fact_id", how="left")
        .with_columns(pl.col("value").fill_null(0.0))
    )
    findings = FindingQuery.build(
        sections,
        pl.concat_str(
            pl.col("opener_count"),
            pl.lit(" of the "),
            pl.col("sentence_count"),
            pl.lit(" sentences in one section open with `"),
            pl.col("opener"),
            pl.lit("`"),
        ),
        (
            ("sentences opening the same way", pl.col("opener_count"), Unit.COUNT),
            ("sentences read", pl.col("sentence_count"), Unit.COUNT),
            ("share of the section", pl.col("share"), Unit.PERCENTAGE),
        ),
        finding_order=pl.col("ordinal"),
        question=pl.concat_str(
            pl.lit("open some of those sentences with something but `"),
            pl.col("opener"),
            pl.lit("`"),
        ),
    )
    return RuleQuery.floating(frame, pl.col("value"), findings=findings)
