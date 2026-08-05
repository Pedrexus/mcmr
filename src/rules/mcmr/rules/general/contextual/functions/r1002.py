from enum import StrEnum, auto

import polars as pl

from ..... import Category, rule
from .....execution import ClassificationBackend
from .....execution.queries import ModelQuery
from .....facts import FunctionFact
from .....table import Table


class _EffectVisibility(StrEnum):
    EXPLICIT = auto()
    HIDDEN = auto()
    PURPOSEFUL = auto()
    UNCERTAIN = auto()


@rule(
    "ALL-FUNC1002",
    policy=Category.outcomes(
        _EffectVisibility,
        good={_EffectVisibility.EXPLICIT, _EffectVisibility.PURPOSEFUL},
        neutral={_EffectVisibility.UNCERTAIN},
    ),
)
def effect_visibility(
    subject: Table[FunctionFact],
    backend: ClassificationBackend,
) -> ModelQuery[_EffectVisibility]:
    """Judge whether a function makes its material effects apparent.

    Definition
    ----------
    Compare names, return values, mutations, I/O, global access, transactions, and caller
    expectations. The rule judges surprise rather than forbidding side effects. The criteria
    independently establish a material effect, explicit disclosure, a query-like interface,
    and a protocol convention. Only query-like names need model judgment because command names
    already disclose that work may change external state.

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
    return backend.classification(
        subject,
        category=_EffectVisibility,
        instructions=effect_visibility.instructions,
    ).where(
        pl.col("name").str.contains(
            r"^(can|calculate|check|compute|describe|fetch|find|format|get|has|inspect|is|iter|"
            r"list|load|lookup|parse|read|render|should|validate)"
        )
        & (pl.col("behavior_operation_count") >= 2)
        & (pl.col("direct_statement_count") >= 2)
        & ~pl.col("is_test")
        & ~pl.col("is_abstract")
        & ~pl.col("is_protocol_member")
        & ~pl.col("is_pass_body"),
        requires=(
            "behavior_operation_count",
            "direct_statement_count",
            "is_test",
            "is_abstract",
            "is_protocol_member",
            "is_pass_body",
            "name",
        ),
    )
