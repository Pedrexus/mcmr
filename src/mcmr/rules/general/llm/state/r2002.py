from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import StateFact


class TemporalCoupling(StrEnum):
    EXPLICIT = auto()
    HIDDEN = auto()
    INTRINSIC = auto()
    AVOIDABLE = auto()
    UNCERTAIN = auto()


@rule
async def temporal_coupling(
    subject: StateFact,
    backend: ClassificationBackend,
) -> TemporalCoupling:
    """Judge whether required operation order is explicit and justified.

    Definition
    ----------
    Compare legal states, constructors, method order, hidden flags, failure modes, and possible
    designs that make invalid sequences unrepresentable.

    Evidence
    --------
    Findings cite state transitions, callers, ordering assumptions, failures, and alternatives.

    Exceptions
    ----------
    Stateful protocols may require order when the API represents each state clearly.

    Examples
    --------
    Requiring `configure` before `run` while both methods remain callable is `hidden`. A session
    object returned only after successful configuration makes the sequence explicit.

    References
    ----------
    Cites "The Pragmatic Programmer", temporal coupling
    Cites "Refactoring", Mutable Data
    Cites "Domain-Driven Design", making implicit concepts explicit
    """
    return await backend.classify(
        subject,
        category=TemporalCoupling,
        instructions=(
            "Compare legal states, constructors, method order, hidden flags, failure"
            "modes, and possible designs that make invalid sequences unrepresentable."
        ),
    )
