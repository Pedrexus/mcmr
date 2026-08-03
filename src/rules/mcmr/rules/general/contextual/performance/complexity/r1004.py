from enum import StrEnum, auto

import polars as pl

from ...... import Category, rule
from ......execution import ClassificationBackend
from ......execution.queries import ModelQuery
from ......facts import FunctionFact
from ......table import FunctionRelation, Table


class _AlgorithmicComplexity(StrEnum):
    PROPORTIONATE = auto()
    RISKY = auto()
    AVOIDABLE = auto()
    TRADEOFF = auto()
    UNCERTAIN = auto()


@rule(
    "ALL-PERF1004",
    policy=Category.outcomes(
        _AlgorithmicComplexity,
        good={_AlgorithmicComplexity.PROPORTIONATE},
        neutral={_AlgorithmicComplexity.TRADEOFF, _AlgorithmicComplexity.UNCERTAIN},
    ),
)
def algorithmic_complexity(
    subject: Table[FunctionFact],
    backend: ClassificationBackend,
) -> ModelQuery[_AlgorithmicComplexity]:
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
    query = backend.classification(
        subject,
        category=_AlgorithmicComplexity,
        instructions=algorithmic_complexity.instructions,
    )
    if subject.relation_type is not FunctionRelation:
        return query.where(
            ((pl.col("control_increments.length") > 0) | pl.col("is_recursive"))
            & ~pl.col("is_test"),
            requires=("control_increments.length", "is_recursive", "is_test"),
        )
    loops = subject.lazy(FunctionRelation.CONTROLS).filter(pl.col("kind") == "loop")
    functions = subject.lazy(FunctionRelation.FUNCTIONS).filter(~pl.col("is_test"))
    selected = pl.concat(
        (
            functions.join(
                loops.select("function_id").unique(),
                left_on="entity_id",
                right_on="function_id",
                how="semi",
            ).select("fact_id"),
            functions.filter(pl.col("is_recursive")).select("fact_id"),
        )
    )
    return query.matching(selected)
