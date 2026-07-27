from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import TestStrategyFact


class TestStrategy(StrEnum):
    SUFFICIENT = auto()
    GAPS = auto()
    OVERBUILT = auto()
    MISALIGNED = auto()
    UNCERTAIN = auto()


@rule
async def test_strategy(
    subject: TestStrategyFact,
    backend: ClassificationBackend,
) -> TestStrategy:
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
    return await backend.classify(
        subject,
        category=TestStrategy,
        instructions=(
            "Compare requirements, risks, boundaries, failures, test types, runtime,"
            "coverage, and mutation evidence. The rule evaluates strategy rather than"
            "maximizing test count."
        ),
    )
