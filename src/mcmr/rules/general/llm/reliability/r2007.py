from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import RetryPolicyFact


class BackoffQuality(StrEnum):
    ROBUST = auto()
    PARTIAL = auto()
    SYNCHRONIZED = auto()
    UNBOUNDED = auto()
    NOT_NEEDED = auto()
    UNCERTAIN = auto()


@rule
async def backoff_quality(
    subject: RetryPolicyFact,
    backend: ClassificationBackend,
) -> BackoffQuality:
    """Judge whether retry backoff avoids synchronization and unbounded delay.

    Definition
    ----------
    Ask the selected judgment backend for six independently cited facts about client population,
    delay progression, jitter, server hints, deadline caps, and the bounded local retry exception.
    Reduce those answers through a fixed table. The model never selects the final category.

    Evidence
    --------
    The frozen evidence bundle contains formulas, caps, hints, deadlines, traces, and retry timing.
    Every yes or no answer requires a valid evidence ID. Missing, conflicting, duplicate, or
    uncited answers remain `unknown` and reduce to `uncertain`.

    Exceptions
    ----------
    One bounded local retry may not need randomized backoff when no shared resource is contested.

    Examples
    --------
    Capped exponential backoff with full jitter and deadline clipping is `robust`. Fixed
    one-second retries across thousands of workers are `synchronized`. Exactly one immediate
    contention-free local retry is `not_needed`.

    References
    ----------
    Cites "The Amazon Builders Library", Exponential Backoff and Jitter
    Cites "Site Reliability Engineering", addressing cascading failures
    Cites "gRPC documentation", retry design
    """
    return await backend.classify(
        subject,
        category=BackoffQuality,
        instructions=(
            "Ask the selected judgment backend for six independently cited facts about"
            "client population, delay progression, jitter, server hints, deadline caps,"
            "and the bounded local retry exception. Reduce those answers through a fixed"
            "table. The model never selects the final category."
        ),
    )
