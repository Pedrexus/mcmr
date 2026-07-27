from ..... import rule
from .....facts import ProseSegmentFact
from .....models import Percentage


@rule
def paragraph_length_uniformity(
    subject: ProseSegmentFact,
    *,
    minimum_paragraphs: int = 4,
    minimum_words: int = 30,
) -> Percentage:
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
    eligible = [
        section.paragraph_word_counts.at_least(minimum_words) for section in subject.sections
    ]
    return max(
        (counts.uniformity() for counts in eligible if len(counts) >= minimum_paragraphs),
        default=0.0,
    )
