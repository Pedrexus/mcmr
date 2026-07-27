from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import SymbolFact


class AttributeVisibility(StrEnum):
    PUBLIC = auto()
    JUSTIFIED_NON_PUBLIC = auto()
    JUSTIFIED_NAME_MANGLING = auto()
    DOCUMENTED_DUNDER = auto()
    UNJUSTIFIED_NON_PUBLIC = auto()
    INVALID_DUNDER = auto()
    UNCERTAIN = auto()


@rule
async def attribute_visibility(
    subject: SymbolFact,
    backend: ClassificationBackend,
) -> AttributeVisibility:
    """Judge whether one Python name should be public or non-public.

    Definition
    ----------
    Public is the project default. One leading underscore is justified only for an
    implementation detail that carries no public compatibility promise. Two leading
    underscores are justified only to prevent accidental subclass name collisions.
    Double-leading-and-trailing names must be documented Python special names.

    Evidence
    --------
    The finding retains the supplied role, usage context, source path, and model confidence.

    Exceptions
    ----------
    Framework contracts, generated code, imported compatibility surfaces, and explicitly
    documented public or subclass APIs may require a particular spelling.

    Examples
    --------
    `cache` is `public` by default. `_cache` needs evidence that callers must not depend on it.
    `__cache` is reserved for preventing accidental subclass collisions.

    References
    ----------
    Cites "The Python Tutorial", section 9.6 on private variables
    Cites "PEP 8, Style Guide for Python Code", naming conventions and designing for inheritance
    """
    return await backend.classify(
        subject,
        category=AttributeVisibility,
        instructions=(
            "Public is the project default. One leading underscore is justified only for"
            "an implementation detail that carries no public compatibility promise. Two"
            "leading underscores are justified only to prevent accidental subclass name"
            "collisions. Double-leading-and-trailing names must be documented Python"
            "special names."
        ),
    )
