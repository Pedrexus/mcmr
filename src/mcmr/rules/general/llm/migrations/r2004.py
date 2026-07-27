from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import MigrationFact


class DataVerification(StrEnum):
    COMPLETE = auto()
    PARTIAL = auto()
    WEAK = auto()
    ABSENT = auto()
    NOT_REQUIRED = auto()
    UNCERTAIN = auto()


@rule
async def data_verification(
    subject: MigrationFact,
    backend: ClassificationBackend,
) -> DataVerification:
    """Judge whether migration verification can detect material data errors.

    Definition
    ----------
    Ask the selected judgment backend for five independently cited verification facts and reduce
    them through a fixed decision table. Compare source and destination populations, invariants,
    checksums, reconciliation, sampling, duplicates, orphans, and retained audit evidence.

    Evidence
    --------
    The frozen bundle cites datasets, invariants, queries, samples, discrepancies, and acceptance
    thresholds. Missing, duplicate, conflicting, or uncited answers remain `unknown` and reduce to
    `uncertain`.

    Exceptions
    ----------
    Full deterministic comparison may replace sampling when it is safe and computationally bound.

    Examples
    --------
    Reconciled values, business invariants, and orphan detection can be `complete`. Comparing only
    row counts is `weak` when values or associations can be corrupted unnoticed.

    References
    ----------
    Cites "Refactoring Databases", data migration patterns
    Cites "Evolutionary Database Design"
    Cites "Site Reliability Engineering", data integrity
    """
    return await backend.classify(
        subject,
        category=DataVerification,
        instructions=(
            "Ask the selected judgment backend for five independently cited verification"
            "facts and reduce them through a fixed decision table. Compare source and"
            "destination populations, invariants, checksums, reconciliation, sampling,"
            "duplicates, orphans, and retained audit evidence."
        ),
    )
