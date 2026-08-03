from pydantic import NonNegativeInt

from ...... import Numeric, rule
from ......facts import ProseSegmentFact
from ......query import PercentageQuery
from ......table import Table
from ..prose_relations import ProseRelations, percentage_query


@rule("ALL-WRIT0003", policy=Numeric(maximum=90))
def sentence_length_uniformity(
    subject: Table[ProseSegmentFact],
    *,
    minimum_sentences: NonNegativeInt = 5,
    minimum_words: NonNegativeInt = 3,
) -> PercentageQuery:
    """Measure uniform sentence length without inferring authorship.

    Definition
    ----------
    Extract the prose sections of a document, excluding code fences, comments, headings, tables,
    block quotations, and list items, and keep the sentences holding at least `minimum_words`
    words. For every section holding at least `minimum_sentences` of them, compute `100 * max(0, 1
    - MAD / mean)` over the sentence word counts, where MAD is the mean absolute deviation. Return
    the highest value any section reaches.

    One hundred means every sentence in some section is the same length. Human prose varies its
    rhythm because the writer is thinking, so a section that does not vary is worth a second look.
    This is a measurement of rhythm and never a claim about who wrote the text, which is why the
    value comes back plain and a project policy decides what to do with it.

    Evidence
    --------
    The finding names the section, its sentence count, and its exact bounded uniformity percentage.
    The value is the highest section uniformity in the document, where one hundred means equal
    sentence lengths and lower values mean more variation.

    Exceptions
    ----------
    A section holding fewer than `minimum_sentences` qualifying sentences is skipped rather than
    measured, because a deviation over three sentences says nothing. Sentences shorter than
    `minimum_words` are dropped first, so a run of headings rendered as prose cannot drive the
    score. A document with no qualifying section at all measures zero rather than one hundred.
    Uniform prose is often deliberate in a reference manual, a translated text, or a templated
    report, so the value is evidence rather than a verdict.

    Examples
    --------
    Five sentences of the same word count return `100`. Sentences of `5`, `10`, `15`, `20`, and
    `25` words have a mean of `15` and a mean absolute deviation of `6`, so they return `60`. A
    section holding four qualifying sentences is skipped under the default `minimum_sentences`, and
    a document of only such sections returns `0`.

    References
    ----------
    Cites "Vale AI Tells", experimental SentenceLengthVariance rule
    https://github.com/tbhb/vale-ai-tells/blob/main/EXPERIMENTAL.md
    Cites "Do LLMs Write Like Humans"
    https://arxiv.org/abs/2410.16107
    """
    frame = ProseRelations(subject).uniformity(
        "sections.sentence_word_counts.root",
        minimum_entries=minimum_sentences,
        minimum_words=minimum_words,
    )
    return percentage_query(frame, "sentence length uniformity")
