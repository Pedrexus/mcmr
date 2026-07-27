from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import AlgorithmFact


class AlgorithmicComplexity(StrEnum):
    PROPORTIONATE = auto()
    RISKY = auto()
    AVOIDABLE = auto()
    TRADEOFF = auto()
    UNCERTAIN = auto()


@rule
async def algorithmic_complexity(
    subject: AlgorithmFact,
    backend: ClassificationBackend,
) -> AlgorithmicComplexity:
    """Judge whether algorithmic growth fits plausible workload bounds.

    Definition
    ----------
    Compare time and space growth, input bounds, constants, allocation, data distribution,
    maintained library alternatives, measured workloads, and performance objectives.

    Evidence
    --------
    Findings cite loops or algorithms, bounds, workloads, profiles, alternatives, and objectives.

    Exceptions
    ----------
    Small verified inputs may justify a simpler algorithm with a worse asymptotic bound.

    Examples
    --------
    A quadratic comparison over unbounded user records is `risky`. A quadratic scan over at most
    eight items is a `tradeoff`, since the bound is what makes the cost affordable. A linear pass
    sized to its input is `proportionate`, and a quadratic step a linear one would replace outright
    is `avoidable`.

    References
    ----------
    Cites "Beyond the Basic Stuff with Python", Measuring Performance and Big O
    Cites "The Algorithm Design Manual"
    Cites "The Pragmatic Programmer", estimate the order of algorithms
    """
    return await backend.classify(
        subject,
        category=AlgorithmicComplexity,
        instructions=(
            "Compare time and space growth, input bounds, constants, allocation, data"
            "distribution, maintained library alternatives, measured workloads, and"
            "performance objectives."
        ),
    )
