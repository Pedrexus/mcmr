from enum import StrEnum, auto

from ..... import Category, rule
from .....execution import ClassificationBackend
from .....execution.queries import ModelQuery
from .....facts import TestStrategyFact
from .....table import Table


class _TestStrategy(StrEnum):
    SUFFICIENT = auto()
    GAPS = auto()
    OVERBUILT = auto()
    MISALIGNED = auto()
    UNCERTAIN = auto()


@rule(
    "ALL-TEST1001",
    policy=Category.outcomes(
        _TestStrategy, good={_TestStrategy.SUFFICIENT}, neutral={_TestStrategy.UNCERTAIN}
    ),
)
def test_strategy(
    subject: Table[TestStrategyFact],
    backend: ClassificationBackend,
) -> ModelQuery[_TestStrategy]:
    """Judge whether tests provide proportionate confidence.

    Definition
    ----------
    Compare requirements, risks, boundaries, failures, test types, runtime, coverage, and
    mutation evidence. The rule evaluates strategy rather than maximizing test count.

    Evidence
    --------
    Findings cite behavior, risk, test, and measurement evidence.

    Exceptions
    ----------
    Prototypes and low-risk scripts may accept lighter evidence by explicit policy.

    Examples
    --------
    A payment path tested at its boundaries and on its failure modes is `sufficient`. The same path
    with no failure test is `gaps`. Repeating one pure-function assertion through unit, service,
    and browser layers is `overbuilt`, and testing the framework rather than the behavior is
    `misaligned`.

    References
    ----------
    Cites "Software Engineering at Google", Testing Overview
    Cites "Test Pyramid"
    Cites "xUnit Test Patterns"
    """
    return backend.classification(
        subject,
        category=_TestStrategy,
        instructions=test_strategy.instructions,
    )
