from enum import StrEnum, auto

import polars as pl

from ..... import Category, rule
from .....domain.contracts import Criterion
from .....execution import ClassificationBackend, CriterionValue
from .....execution.queries import AssessmentContract, ModelQuery
from .....facts import FunctionFact
from .....table import FunctionRelation, Table


class _BoundedWork(StrEnum):
    BOUNDED = auto()
    UNBOUNDED = auto()
    BACKPRESSURED = auto()
    DROPPED = auto()
    UNCERTAIN = auto()


_CRITERIA = (
    Criterion(
        name="input naturally finite", question="Is the maximum input population proven finite?"
    ),
    Criterion(
        name="resources bounded",
        question="Are queues, concurrency, batches, memory, and deadlines bounded?",
    ),
    Criterion(
        name="backpressure propagates",
        question="Can producers observe and respect admission pressure?",
    ),
    Criterion(
        name="overload sheds safely",
        question="Can overload cancel or shed work without uncontrolled growth?",
    ),
)
_TABLE = (
    (
        _BoundedWork.BOUNDED,
        (
            ("input naturally finite", CriterionValue.YES),
            ("resources bounded", CriterionValue.YES),
        ),
    ),
    (
        _BoundedWork.BACKPRESSURED,
        (
            ("input naturally finite", CriterionValue.NO),
            ("resources bounded", CriterionValue.YES),
            ("backpressure propagates", CriterionValue.YES),
        ),
    ),
    (
        _BoundedWork.DROPPED,
        (
            ("input naturally finite", CriterionValue.NO),
            ("overload sheds safely", CriterionValue.YES),
        ),
    ),
    (
        _BoundedWork.UNBOUNDED,
        (("input naturally finite", CriterionValue.NO), ("resources bounded", CriterionValue.NO)),
    ),
)


@rule(
    "ALL-RELI1003",
    policy=Category.outcomes(
        _BoundedWork,
        good={_BoundedWork.BACKPRESSURED, _BoundedWork.BOUNDED},
        neutral={_BoundedWork.UNCERTAIN},
    ),
)
def bounded_work(
    subject: Table[FunctionFact],
    backend: ClassificationBackend,
) -> ModelQuery[_BoundedWork]:
    """Judge whether load can exceed controlled work and resource limits.

    Definition
    ----------
    Ask the selected judgment backend for four independently cited capacity facts and reduce the
    answers through a fixed table. Compare input rates, queues, concurrency, batching, memory,
    deadlines, admission, backpressure, load shedding, cancellation, and overload recovery. The
    model never selects the final category. Candidates must create concurrent work, be async, or
    recurse because an ordinary synchronous loop cannot accumulate independent outstanding work.

    Evidence
    --------
    The frozen evidence bundle contains producers, buffers, workers, limits, resource profiles,
    and overload behavior. Every yes or no answer requires a valid evidence ID. Missing,
    conflicting, duplicate, or uncited answers remain `unknown` and reduce to `uncertain`.

    Exceptions
    ----------
    Finite offline inputs may be naturally bounded when their maximum is verified.

    Examples
    --------
    A bounded worker pool with queue admission is `backpressured`. Creating one task per
    unbounded message with no limit is `unbounded`. A fixed batch whose size is proven is
    `bounded`.

    References
    ----------
    Cites "Site Reliability Engineering", handling overload
    Cites "Reactive Streams specification", backpressure
    Cites "Release It", bulkheads and stability patterns
    """
    query = backend.assessment(
        subject,
        contract=AssessmentContract(
            criteria=list(_CRITERIA),
            instructions=bounded_work.instructions,
            decision_table=_TABLE,
            default=_BoundedWork.UNCERTAIN,
            uncertain=_BoundedWork.UNCERTAIN,
        ),
    )
    if subject.relation_type is not FunctionRelation:
        return query.where(
            (pl.col("is_async") | pl.col("is_recursive") | (pl.col("created_task_count") > 0))
            & ~pl.col("is_test"),
            requires=(
                "is_async",
                "is_recursive",
                "created_task_count",
                "is_test",
            ),
        )
    functions = subject.lazy(FunctionRelation.FUNCTIONS).filter(~pl.col("is_test"))
    selected = functions.filter(
        pl.col("is_async") | pl.col("is_recursive") | (pl.col("created_task_count") > 0)
    ).select("fact_id")
    return query.matching(selected)
