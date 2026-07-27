from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import OperationFact


class Idempotency(StrEnum):
    IDEMPOTENT = auto()
    KEYED = auto()
    NON_IDEMPOTENT = auto()
    COMPENSATED = auto()
    NOT_REQUIRED = auto()
    UNCERTAIN = auto()


@rule
async def idempotency(
    subject: OperationFact,
    backend: ClassificationBackend,
) -> Idempotency:
    """Judge whether replayable operations control duplicate effects.

    Definition
    ----------
    Ask the selected judgment backend for five independently cited replay facts and reduce those
    answers through a fixed table. Compare operation identity, side effects, transactions,
    retries, messages, deduplication, concurrency, response replay, expiration, and compensation.
    The model never selects the final category.

    Evidence
    --------
    The frozen evidence bundle contains entry points, effects, identity keys, storage, retries,
    and duplicate outcomes. Every yes or no answer requires a valid evidence ID. Missing,
    conflicting, duplicate, or uncited answers remain `unknown` and reduce to `uncertain`.

    Exceptions
    ----------
    Strictly local one-shot operations may not need replay protection.

    Examples
    --------
    Creating one payment per durable request key is `keyed`. Retrying an append with no operation
    identity is `non_idempotent`. A one-shot local transformation is `not_required`.

    References
    ----------
    Cites "RFC 9110, HTTP Semantics", idempotent methods
    Cites "Designing Data-Intensive Applications", idempotence and messaging
    Cites "Stripe API documentation", idempotent requests
    """
    return await backend.classify(
        subject,
        category=Idempotency,
        instructions=(
            "Ask the selected judgment backend for five independently cited replay facts"
            "and reduce those answers through a fixed table. Compare operation identity,"
            "side effects, transactions, retries, messages, deduplication, concurrency,"
            "response replay, expiration, and compensation. The model never selects the"
            "final category."
        ),
    )
