from typing import Literal

from ..... import rule
from .....facts import AuthorshipSignalFact


@rule
def authorship_detector_signal(
    subject: AuthorshipSignalFact, *, minimum_words: int = 250
) -> Literal["human_like", "ai_like", "mixed", "inconclusive", "ineligible"]:
    """Report one eligible detector signal as triage rather than proof.

    Definition
    ----------
    Compare the observed word count with both the project minimum and the provider minimum.
    Shorter passages become `ineligible`. Eligible passages retain the provider signal exactly.
    A provider score remains a provider-defined percentage-scale measurement and is never
    renamed as authorship probability.

    Evidence
    --------
    The finding records provider, model, version, calibration domain, word count, provider
    minimum, optional score, and source location. The input must be a frozen observation from a
    detector adapter rather than free-form model prose.

    Exceptions
    ----------
    Distribution shift, editing, paraphrasing, mixed authorship, language, genre, and short text
    can invalidate detector behavior. A signal must not accuse a writer or block publication
    without independent policy and human review. `minimum_words` is the project's own floor, and
    the larger of it and the provider's stated minimum is what a passage has to reach before its
    signal is reported at all.

    Examples
    --------
    An `ai_like` Pangram observation over 800 words remains `ai_like`. The same signal over 80
    words becomes `ineligible` with the default project minimum. A Binoculars score is retained
    only as that detector's raw percentage-scale observation.

    References
    ----------
    Cites "Spotting LLMs With Binoculars"
    https://arxiv.org/abs/2401.12070
    Cites "A Practical Examination of AI-Generated Text Detectors"
    https://arxiv.org/abs/2412.05139
    Cites "Pangram documentation", technical report
    https://arxiv.org/abs/2402.14873
    """
    if subject.assessment is None:
        return "ineligible"
    required_words = max(minimum_words, subject.assessment.minimum_word_count)
    if subject.assessment.observed_word_count < required_words:
        return "ineligible"
    return subject.assessment.signal
