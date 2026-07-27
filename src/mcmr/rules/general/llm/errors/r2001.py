from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import FailurePathFact


class ErrorContext(StrEnum):
    ACTIONABLE = auto()
    OPAQUE = auto()
    EXCESSIVE = auto()
    TRANSLATED = auto()
    UNCERTAIN = auto()


@rule
async def error_context(
    subject: FailurePathFact,
    backend: ClassificationBackend,
) -> ErrorContext:
    """Judge whether failures retain useful and safe diagnostic context.

    Definition
    ----------
    Compare exception cause, operation, identifiers, boundary translation, user message,
    observability, and sensitive data exposure across a failure path. The criteria answer cause
    preservation, operation and subject context, unsafe exposure, and boundary translation
    separately.

    Evidence
    --------
    Findings cite raises, catches, causes, messages, logs, boundary contracts, and redactions.

    Exceptions
    ----------
    Public responses may hide internals while internal evidence securely retains the cause.

    Examples
    --------
    `Unable to save invoice 42` chained from a storage timeout is `actionable`. Replacing every
    failure with `Operation failed` is `opaque`.

    References
    ----------
    Cites "Clean Code", Error Handling
    Cites "The Python Standard Library", exception chaining
    Cites "Site Reliability Engineering", useful failure diagnostics
    """
    return await backend.classify(
        subject,
        category=ErrorContext,
        instructions=(
            "Compare exception cause, operation, identifiers, boundary translation, user"
            "message, observability, and sensitive data exposure across a failure path."
            "The criteria answer cause preservation, operation and subject context,"
            "unsafe exposure, and boundary translation separately."
        ),
    )
