from collections import Counter

from ..... import rule
from .....facts import ProseSegmentFact
from .....models import Choice, Finding, Measurement, PercentageReport, Reported, Unit


@rule
def sentence_opener_concentration(
    subject: ProseSegmentFact,
    *,
    minimum_sentences: int = 6,
    ignored_openers: tuple[str, ...] = ("a", "i"),
) -> PercentageReport:
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
    findings: list[Finding] = []
    ignored = {word.casefold() for word in ignored_openers}
    for section in subject.sections:
        openers = [
            word.casefold() for word in section.sentence_openers if word.casefold() not in ignored
        ]
        if len(openers) < minimum_sentences:
            continue
        counted = Counter(openers)
        word = min(counted, key=lambda opener: (-counted[opener], opener))
        findings.append(
            Finding(
                message=(
                    f"{counted[word]} of the {len(openers)} sentences in one section open with "
                    f"`{word}`"
                ),
                span=subject.span,
                measurements=(
                    Measurement(name="sentences opening the same way", value=counted[word]),
                    Measurement(name="sentences read", value=len(openers)),
                    Measurement(
                        name="share of the section",
                        value=counted[word] / len(openers) * 100.0,
                        unit=Unit.PERCENTAGE,
                    ),
                ),
                repair=Choice(
                    question=f"open some of those sentences with something but `{word}`"
                ),
            )
        )
    return Reported(
        value=max(
            (item.measurements[2].value for item in findings),
            default=0.0,
        ),
        findings=tuple(findings),
    )
