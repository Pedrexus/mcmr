from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import RetryPolicyFact


class RetryEligibility(StrEnum):
    ELIGIBLE = auto()
    CONDITIONAL = auto()
    INELIGIBLE = auto()
    DELEGATED = auto()
    UNCERTAIN = auto()


@rule
async def retry_eligibility(
    subject: RetryPolicyFact,
    backend: ClassificationBackend,
) -> RetryEligibility:
    """Judge whether one failed operation is eligible for automatic retry.

    Definition
    ----------
    Ask the selected judgment backend for five independently cited facts about failure class,
    replay effects, required safety conditions, and retry ownership. Reduce those answers through
    a fixed table. The model never selects the final category.

    Evidence
    --------
    The frozen evidence bundle contains operation contracts, failure modes, effects, keys,
    transactions, and owner layers. Every yes or no answer requires a valid evidence ID. Missing,
    conflicting, duplicate, or uncited answers remain `unknown` and reduce to `uncertain`.

    Exceptions
    ----------
    An otherwise unsafe operation may be conditionally eligible with verified effect
    deduplication or reconciliation.

    Examples
    --------
    A transient idempotent read is `eligible`. Validation failure is `ineligible`. A payment that
    requires a durable idempotency key is `conditional`. A lower transport is `delegated` when an
    application boundary owns retry and receives complete failure detail.

    References
    ----------
    Cites "The Amazon Builders Library", Timeouts, Retries, and Backoff with Jitter
    Cites "Site Reliability Engineering", addressing cascading failures
    Cites "RFC 9110, HTTP Semantics", idempotent methods
    """
    return await backend.classify(
        subject,
        category=RetryEligibility,
        instructions=(
            "Ask the selected judgment backend for five independently cited facts about"
            "failure class, replay effects, required safety conditions, and retry"
            "ownership. Reduce those answers through a fixed table. The model never"
            "selects the final category."
        ),
    )
