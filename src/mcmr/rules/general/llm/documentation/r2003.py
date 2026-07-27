from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import DecisionRecordFact


class DecisionTraceability(StrEnum):
    TRACEABLE = auto()
    MISSING = auto()
    STALE = auto()
    EXCESSIVE = auto()
    UNCERTAIN = auto()


@rule
async def decision_traceability(
    subject: DecisionRecordFact,
    backend: ClassificationBackend,
) -> DecisionTraceability:
    """Judge whether consequential engineering decisions remain explainable.

    Definition
    ----------
    Compare current architecture, constraints, alternatives, decisions, owners, consequences,
    and superseding evidence. The rule targets durable choices rather than documenting everything.
    The criteria independently establish consequence, recoverable rationale, ownership links,
    contradiction with the current system, and low-impact record burden.

    Evidence
    --------
    Findings cite code or system consequences and the decision records that explain them.

    Exceptions
    ----------
    Local reversible implementation choices do not require durable decision records.

    Examples
    --------
    A storage backend choice linked to constraints and a superseding review is `traceable`. A
    load-bearing custom protocol with no rationale is `missing`.

    References
    ----------
    Cites "Documenting Architecture Decisions"
    Cites "ISO IEC IEEE 42010", architecture decision rationale
    Cites "The Pragmatic Programmer", knowledge and communication
    """
    return await backend.classify(
        subject,
        category=DecisionTraceability,
        instructions=(
            "Compare current architecture, constraints, alternatives, decisions, owners,"
            "consequences, and superseding evidence. The rule targets durable choices"
            "rather than documenting everything. The criteria independently establish"
            "consequence, recoverable rationale, ownership links, contradiction with the"
            "current system, and low-impact record burden."
        ),
    )
