from pydantic import NonNegativeInt

from ...... import Numeric, rule
from ......facts import ProseSegmentFact
from ......query import PercentageQuery
from ......table import Table
from ..prose_relations import ProseRelations, percentage_query


@rule("ALL-WRIT0004", policy=Numeric(maximum=90))
def paragraph_length_uniformity(
    subject: Table[ProseSegmentFact],
    *,
    minimum_paragraphs: NonNegativeInt = 4,
    minimum_words: NonNegativeInt = 30,
) -> PercentageQuery:
    """Measure uniform paragraph length without inferring authorship.

    Definition
    ----------
    Split each prose section at blank lines once the non-prose blocks are removed, and keep the
    paragraphs holding at least `minimum_words` words. For every section holding at least
    `minimum_paragraphs` of them, compute `100 * max(0, 1 - MAD / mean)` over the paragraph word
    counts and return the highest value any section reaches.

    Paragraph rhythm is the same observation as sentence rhythm one level up. A writer working
    through an argument spends more words where the idea is harder, so paragraphs of identical
    weight suggest a template rather than a train of thought. It is a pacing measurement and never
    an authorship claim.

    Evidence
    --------
    The finding names each section, its paragraph count, and its bounded uniformity percentage. The
    value is the highest section uniformity in the document, and equal paragraph lengths produce
    one hundred.

    Exceptions
    ----------
    A section holding fewer than `minimum_paragraphs` qualifying paragraphs is skipped rather than
    measured. Paragraphs under `minimum_words` are dropped first, so a run of one-line notes cannot
    drive the score. Templates, reference manuals, release notes, and deliberately parallel
    explanations are uniform because the form calls for it, so a high value there is a description
    rather than a defect.

    Examples
    --------
    Four paragraphs of fifty words each return `100`. Paragraphs of `30`, `45`, `70`, and `100`
    words have a mean of about `61` and a mean absolute deviation of about `23`, so they return
    about `62`. A section holding three qualifying paragraphs is skipped under the default
    `minimum_paragraphs`.

    References
    ----------
    Cites "Vale AI Tells", experimental ParagraphLengthVariance rule
    https://github.com/tbhb/vale-ai-tells/blob/main/EXPERIMENTAL.md
    Cites "Pangram documentation", AI writing patterns
    https://www.pangram.com/blog/pangram-ai-phrases
    """
    frame = ProseRelations(subject).uniformity(
        "sections.paragraph_word_counts.root",
        minimum_entries=minimum_paragraphs,
        minimum_words=minimum_words,
    )
    return percentage_query(frame, "paragraph length uniformity")
