from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import ComponentFact


class ComponentBalance(StrEnum):
    BALANCED = auto()
    OVERSIZED = auto()
    FRAGMENTED = auto()
    ASYMMETRIC = auto()
    UNCERTAIN = auto()


@rule
async def component_balance(
    subject: ComponentFact,
    backend: ClassificationBackend,
) -> ComponentBalance:
    """Judge whether component boundaries create a maintainable size distribution.

    Definition
    ----------
    Compare source volume, public surface, responsibilities, dependencies, churn, navigation,
    and ownership across peer packages. Size is evidence rather than an automatic violation.
    The criteria separately establish coherence, concentrated work, navigation cost, and a
    deliberate reason for asymmetric size.

    Evidence
    --------
    Findings cite component metrics, responsibilities, edges, changes, and navigation costs.

    Exceptions
    ----------
    Generated components and intentionally thin adapters may be asymmetric.

    Examples
    --------
    One package owning most unrelated application behavior is `oversized`. Splitting every small
    value type into a package can be `fragmented`.

    References
    ----------
    Cites "Building Maintainable Software", balance component size
    Cites "A Philosophy of Software Design", deep modules
    Cites "Clean Architecture"
    """
    return await backend.classify(
        subject,
        category=ComponentBalance,
        instructions=(
            "Compare source volume, public surface, responsibilities, dependencies,"
            "churn, navigation, and ownership across peer packages. Size is evidence"
            "rather than an automatic violation. The criteria separately establish"
            "coherence, concentrated work, navigation cost, and a deliberate reason for"
            "asymmetric size."
        ),
    )
