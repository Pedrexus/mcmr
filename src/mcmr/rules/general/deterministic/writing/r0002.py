from ..... import rule
from .....facts import AuthorshipSignalFact
from .....models import Percentage


@rule
def ai_associated_segment_coverage(
    subject: AuthorshipSignalFact, *, providers: tuple[str, ...] = ()
) -> Percentage:
    """Measure how much eligible prose contains AI-associated style evidence.

    Definition
    ----------
    Divide the number of declared prose segments containing at least one selected external
    pattern by the total number of declared eligible segments, then multiply by one hundred.
    Each segment contributes at most once even when it contains many patterns. No segments
    produces zero percent.

    Evidence
    --------
    Findings name every covered segment and its selected occurrence count. Segment identity, scope,
    and source range come from the frozen writing evidence artifact. The value is the percentage of
    eligible segments holding at least one selected pattern.

    Exceptions
    ----------
    Coverage measures distribution rather than severity or authorship. One repeated phrase spread
    across many short comments can have higher coverage than many phrases in one long article.
    Projects should choose segment boundaries that match their review policy. `providers` selects
    which analyzers count, and an empty selection includes every provider the evidence holds.

    Examples
    --------
    Patterns in one of four eligible segments return `25`. Twenty patterns confined to one
    declared document segment return `100`, while the separate pattern-count rule returns
    `20`.

    References
    ----------
    Cites "Pangram documentation", evidence interface
    https://www.pangram.com/blog/pangram-ai-phrases
    Cites "Vale AI Tells"
    https://github.com/tbhb/vale-ai-tells
    """
    eligible = [segment for segment in subject.segments if segment.is_eligible]
    if not eligible:
        return 0.0
    matched = sum(
        any(
            patterns and (not providers or provider in providers)
            for provider, patterns in segment.patterns_by_provider.items()
        )
        for segment in eligible
    )
    return matched / len(eligible) * 100.0
