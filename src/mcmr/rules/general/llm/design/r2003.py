from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import DesignStructureFact


class ExtensionDesign(StrEnum):
    EXTENSIBLE = auto()
    RIGID = auto()
    SPECULATIVE = auto()
    INTENTIONALLY_CLOSED = auto()
    UNCERTAIN = auto()


@rule
async def extension_design(
    subject: DesignStructureFact,
    backend: ClassificationBackend,
) -> ExtensionDesign:
    """Judge whether an established variation can grow without destabilizing policy.

    Definition
    ----------
    Compare current variants, recent additions, branch or type dispatch, edits to stable policy,
    extension contracts, tests, and added indirection. Open closed design means that a demonstrated
    variation usually grows through new code while stable policy remains unchanged. It does not
    require extension machinery for hypothetical change. The criteria separately establish the
    variation axis, extension contract, edits to stable policy, and a justified closed set.

    Evidence
    --------
    Findings cite the variation axis, peer implementations, change history, edited policy units,
    dispatch sites, extension contracts, and direct alternatives.

    Exceptions
    ----------
    Security boundaries, wire protocols, exhaustive domain states, and intentionally finite models
    may be closed to extension. Framework-owned extension mechanisms may constrain the local shape.

    Examples
    --------
    Adding a fourth payment method as one new strategy behind an existing contract is `extensible`.
    Editing six conditionals across pricing policy for every new customer class is `rigid`. A
    plugin registry around one implementation with no expected peer is `speculative`.

    References
    ----------
    Cites "Agile Software Development", Open Closed Principle
    Cites "Design Principles and Design Patterns", Open Closed Principle
    Cites "Software Engineering at Google", SOLID and Open Closed design
    """
    return await backend.classify(
        subject,
        category=ExtensionDesign,
        instructions=(
            "Compare current variants, recent additions, branch or type dispatch, edits"
            "to stable policy, extension contracts, tests, and added indirection. Open"
            "closed design means that a demonstrated variation usually grows through new"
            "code while stable policy remains unchanged. It does not require extension"
            "machinery for hypothetical change. The criteria separately establish the"
            "variation axis, extension contract, edits to stable policy, and a justified"
            "closed set."
        ),
    )
