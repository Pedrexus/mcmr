from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import RetryPolicyFact


class RetryBudget(StrEnum):
    ADEQUATE = auto()
    EXCESSIVE = auto()
    INSUFFICIENT = auto()
    COMPETING = auto()
    ABSENT = auto()
    UNCERTAIN = auto()


@rule
async def retry_budget(
    subject: RetryPolicyFact,
    backend: ClassificationBackend,
) -> RetryBudget:
    """Judge whether retry work stays within an end-to-end budget.

    Definition
    ----------
    Ask the selected judgment backend for five independently cited retry facts. Reduce those
    answers through the fixed decision table above. The model never selects the final category.
    Compare caller deadlines, per-attempt timeouts, attempt caps, concurrent load, downstream
    cost, recovery intervals, retry layers, and cancellation propagation.

    Evidence
    --------
    The frozen evidence bundle contains retry configuration, call paths, deadlines, observed
    recovery timing, and capacity limits. Every yes or no answer requires a valid evidence ID.
    Missing, conflicting, duplicate, or uncited answers remain `unknown` and reduce to
    `uncertain`.

    Exceptions
    ----------
    Offline work may use longer budgets when capacity, ownership, and abandonment remain bound.

    Examples
    --------
    Two attempts inside a propagated deadline can be `adequate`. Three retries at each of four
    nested layers are `competing` even when every layer has a local limit. A retry loop with no
    attempt, time, or load cap is `absent`.

    References
    ----------
    Cites "The Amazon Builders Library", Timeouts, Retries, and Backoff with Jitter
    Cites "Site Reliability Engineering", handling overload
    Cites "Release It", stability patterns
    """
    return await backend.classify(
        subject,
        category=RetryBudget,
        instructions=(
            "Ask the selected judgment backend for five independently cited retry facts."
            "Reduce those answers through the fixed decision table above. The model never"
            "selects the final category. Compare caller deadlines, per-attempt timeouts,"
            "attempt caps, concurrent load, downstream cost, recovery intervals, retry"
            "layers, and cancellation propagation."
        ),
    )
