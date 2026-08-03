from enum import StrEnum, auto

import polars as pl

from ..... import Category, rule
from .....execution import ClassificationBackend
from .....execution.queries import ModelQuery
from .....facts import ClassFact
from .....table import Table


class _TemporalCoupling(StrEnum):
    EXPLICIT = auto()
    HIDDEN = auto()
    INTRINSIC = auto()
    AVOIDABLE = auto()
    UNCERTAIN = auto()


@rule(
    "ALL-STAT1002",
    policy=Category.outcomes(
        _TemporalCoupling,
        good={_TemporalCoupling.EXPLICIT, _TemporalCoupling.INTRINSIC},
        neutral={_TemporalCoupling.UNCERTAIN},
    ),
)
def temporal_coupling(
    subject: Table[ClassFact],
    backend: ClassificationBackend,
) -> ModelQuery[_TemporalCoupling]:
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
    return backend.classification(
        subject,
        category=_TemporalCoupling,
        instructions=temporal_coupling.instructions,
    ).where(
        pl.col("has_instance_fields") & (pl.col("methods.length") >= 2) & ~pl.col("is_test"),
        requires=("has_instance_fields", "methods.length", "is_test"),
    )
