from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import FunctionFact


class EffectVisibility(StrEnum):
    EXPLICIT = auto()
    HIDDEN = auto()
    PURPOSEFUL = auto()
    UNCERTAIN = auto()


@rule
async def effect_visibility(
    subject: FunctionFact,
    backend: ClassificationBackend,
) -> EffectVisibility:
    """Judge whether a function makes its material effects apparent.

    Definition
    ----------
    Compare names, return values, mutations, I/O, global access, transactions, and caller
    expectations. The rule judges surprise rather than forbidding side effects. The criteria
    independently establish a material effect, explicit disclosure, a query-like interface,
    and a protocol convention.

    Evidence
    --------
    Findings cite writes, external calls, names, contracts, and affected callers.

    Exceptions
    ----------
    Python protocol methods and framework hooks may carry conventional effects that callers know.

    Examples
    --------
    `load_profile` that silently updates a database is `hidden`. `save_profile` that commits one
    documented transaction is `explicit`.

    References
    ----------
    Cites "Clean Code", Functions and side effects
    Cites "Command Query Separation"
    Cites "Programming Clojure", values and explicit state
    """
    return await backend.classify(
        subject,
        category=EffectVisibility,
        instructions=(
            "Compare names, return values, mutations, I/O, global access, transactions,"
            "and caller expectations. The rule judges surprise rather than forbidding"
            "side effects. The criteria independently establish a material effect,"
            "explicit disclosure, a query-like interface, and a protocol convention."
        ),
    )
