from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import RetryPolicyFact


class RetrySafety(StrEnum):
    SAFE = auto()
    AMPLIFYING = auto()
    FUTILE = auto()
    MISSING = auto()
    NOT_NEEDED = auto()
    UNCERTAIN = auto()


@rule
async def retry_safety(
    subject: RetryPolicyFact,
    backend: ClassificationBackend,
) -> RetrySafety:
    """Judge whether retry behavior improves reliability without amplifying failure.

    Definition
    ----------
    Ask the selected judgment backend for nine independently cited retry facts. Reduce the
    answers through the fixed decision table above. The model never chooses the final category.
    Compare failure classes, operation effects, idempotency, deadlines, retry layers, load,
    backoff, and observability.

    Evidence
    --------
    The frozen evidence bundle contains retry configuration, failure contracts, call paths,
    effects, budgets, and observed recovery behavior. Every yes or no answer requires a valid
    evidence ID. Missing, conflicting, duplicate, or uncited answers remain `unknown` and reduce
    to `uncertain`.

    Exceptions
    ----------
    A higher layer may own retry when lower layers preserve enough failure information and do not
    also retry independently.

    Examples
    --------
    Retrying a timed-out idempotent read with a shared deadline and bounded jitter can be `safe`.
    Retrying an unkeyed payment at several layers is `amplifying`. Retrying malformed input is
    `futile`.

    References
    ----------
    Cites "The Amazon Builders Library", Timeouts, Retries, and Backoff with Jitter
    Cites "Site Reliability Engineering", addressing cascading failures
    Cites "Release It", stability patterns
    """
    return await backend.classify(
        subject,
        category=RetrySafety,
        instructions=(
            "Ask the selected judgment backend for nine independently cited retry facts."
            "Reduce the answers through the fixed decision table above. The model never"
            "chooses the final category. Compare failure classes, operation effects,"
            "idempotency, deadlines, retry layers, load, backoff, and observability."
        ),
    )
