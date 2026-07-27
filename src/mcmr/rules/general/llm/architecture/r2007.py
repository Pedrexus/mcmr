from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import HotspotFact


class MaintenanceHotspot(StrEnum):
    HEALTHY = auto()
    HOTSPOT = auto()
    STABLE_COMPLEX = auto()
    TRANSIENT = auto()
    UNCERTAIN = auto()


@rule
async def maintenance_hotspot(
    subject: HotspotFact,
    backend: ClassificationBackend,
) -> MaintenanceHotspot:
    """Judge whether change pressure and structural risk form a maintenance hotspot.

    Definition
    ----------
    Combine churn, authorship, complexity, coupling, defects, tests, and current project role.
    High complexity alone or high churn alone does not establish a hotspot. The criteria keep
    change frequency, structural risk, verification, ownership, and transient work independent.

    Evidence
    --------
    Findings cite history windows, structural metrics, defect links, ownership, and test evidence.

    Exceptions
    ----------
    Generated sources, migrations, and short-lived coordinated rewrites may be transient.

    Examples
    --------
    A complex pricing module changed weekly with weak mutation results is a `hotspot`. A parser
    changed once for a protocol revision is `stable_complex`. A module that is complex and quiet,
    or busy and simple, is `healthy`, since neither half establishes a hotspot on its own.

    References
    ----------
    Cites "Your Code as a Crime Scene"
    Cites "CodeScene documentation", behavioral code analysis concepts
    Cites "Use of Relative Code Churn Measures to Predict System Defect Density"
    """
    return await backend.classify(
        subject,
        category=MaintenanceHotspot,
        instructions=(
            "Combine churn, authorship, complexity, coupling, defects, tests, and current"
            "project role. High complexity alone or high churn alone does not establish a"
            "hotspot. The criteria keep change frequency, structural risk, verification,"
            "ownership, and transient work independent."
        ),
    )
