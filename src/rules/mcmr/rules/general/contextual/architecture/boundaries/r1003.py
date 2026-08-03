from enum import StrEnum, auto

import polars as pl

from ...... import Category, rule
from ......execution import ClassificationBackend
from ......execution.queries import ModelQuery
from ......facts import ModuleCouplingFact
from ......table import Table


class _DependencyHubQuality(StrEnum):
    STABLE_ABSTRACTION = auto()
    INTENTIONAL_COORDINATOR = auto()
    DEPENDENCY_MAGNET = auto()
    UNCERTAIN = auto()


@rule(
    "ALL-ARCH1003",
    policy=Category.outcomes(
        _DependencyHubQuality,
        good={
            _DependencyHubQuality.INTENTIONAL_COORDINATOR,
            _DependencyHubQuality.STABLE_ABSTRACTION,
        },
        neutral={_DependencyHubQuality.UNCERTAIN},
    ),
)
def dependency_hub_quality(
    subject: Table[ModuleCouplingFact],
    backend: ClassificationBackend,
) -> ModelQuery[_DependencyHubQuality]:
    """Judge the role of one deterministically nominated dependency hub.

    Definition
    ----------
    Apply only after graph metrics establish a comparable degree outlier. Judge contract
    cohesion, stability across representative changes, consumer-specific knowledge, and a
    deliberate coordination role independently. High degree alone is never a failure.

    Evidence
    --------
    Findings cite graph degrees, focused node relationships, public surface, consumers, and
    representative changes. Whole-repository orientation may locate the hub but cannot prove
    consumer-specific knowledge by itself.

    Exceptions
    ----------
    Stable abstractions, facades, application services, and composition roots are useful hubs.

    Examples
    --------
    A small repository protocol many services import is a `stable_abstraction`. A `Manager` class
    carrying unrelated consumer flags and a branch per caller is a `dependency_magnet`. An
    application service deliberately wiring several collaborators is an `intentional_coordinator`,
    and a hub with no evidence about consumer knowledge is `uncertain`.

    References
    ----------
    Cites "Clean Architecture", stable dependencies principle
    Cites "A Philosophy of Software Design", deep modules
    Cites "Agile Software Development", dependency inversion principle
    """
    high_degree = (pl.col("afferent_count") >= 3) & (
        pl.col("afferent_count") >= pl.col("afferent_count").quantile(0.9, interpolation="nearest")
    )
    return backend.classification(
        subject,
        category=_DependencyHubQuality,
        instructions=dependency_hub_quality.instructions,
    ).where(
        high_degree,
        requires=("afferent_count",),
    )
