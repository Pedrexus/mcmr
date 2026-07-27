from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import ClassFact


class InheritanceDesign(StrEnum):
    SUBTYPE = auto()
    MIXIN = auto()
    COMPOSITION = auto()
    FRAMEWORK = auto()
    UNCERTAIN = auto()


@rule
async def inheritance_design(
    subject: ClassFact,
    backend: ClassificationBackend,
) -> InheritanceDesign:
    """Judge whether inheritance is preferable to composition.

    Definition
    ----------
    Compare substitutability, inherited API surface, state coupling, override needs, variation,
    reuse, and framework requirements before accepting an inheritance relationship. The criteria
    separately establish substitution, a focused mixin, a lower-coupling composition, and a
    mandatory framework extension point.

    Evidence
    --------
    Findings cite bases, overrides, inherited members, callers, and plausible composed designs.

    Exceptions
    ----------
    Small protocol mixins and required framework base classes may be appropriate.

    Examples
    --------
    `CsvReport(Report)` is a `subtype` when every client holding a `Report` can be handed one.
    Inheriting from a database client only to reuse its connection helpers is `composition`, since
    nothing substitutes there. A small `TimestampMixin` contributing one method is a `mixin`, and a
    base a framework requires is `framework`.

    References
    ----------
    Cites "Fluent Python", Inheritance For Better or For Worse
    Cites "Design Patterns", favor object composition over class inheritance
    Cites "Refactoring", Replace Superclass with Delegate
    """
    return await backend.classify(
        subject,
        category=InheritanceDesign,
        instructions=(
            "Compare substitutability, inherited API surface, state coupling, override"
            "needs, variation, reuse, and framework requirements before accepting an"
            "inheritance relationship. The criteria separately establish substitution, a"
            "focused mixin, a lower-coupling composition, and a mandatory framework"
            "extension point."
        ),
    )
