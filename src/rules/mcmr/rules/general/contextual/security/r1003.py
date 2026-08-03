from enum import StrEnum, auto

from ..... import Category, rule
from .....execution import ClassificationBackend
from .....execution.queries import ModelQuery
from .....facts import SecurityBoundaryFact
from .....table import Table


class _ThreatModelCoverage(StrEnum):
    """Classify whether retained threat evidence covers the relevant boundaries."""

    COMPLETE = auto()
    GAPS = auto()
    STALE = auto()
    MISALIGNED = auto()
    INHERITED = auto()
    NOT_REQUIRED = auto()
    UNCERTAIN = auto()


@rule(
    "ALL-SECU1003",
    policy=Category.outcomes(
        _ThreatModelCoverage,
        good={
            _ThreatModelCoverage.COMPLETE,
            _ThreatModelCoverage.INHERITED,
            _ThreatModelCoverage.NOT_REQUIRED,
        },
        neutral={_ThreatModelCoverage.UNCERTAIN},
    ),
)
def threat_model_coverage(
    subject: Table[SecurityBoundaryFact],
    backend: ClassificationBackend,
) -> ModelQuery[_ThreatModelCoverage]:
    """Judge whether current threat analysis covers each relevant security boundary.

    Definition
    ----------
    Compare in-scope boundaries with their assets, flows, actors, threats, mitigations, residual
    risks, ownership, review age, and any named inherited model. Judge whether the evidence covers
    the actual boundary rather than counting a generic checklist.

    Evidence
    --------
    Findings cite raw boundary and threat evidence, including the owner, review age, and inherited
    model when one supplies the analysis.

    Exceptions
    ----------
    A component may inherit a current parent threat model when the retained evidence names it and
    shows that its boundary is covered. A repository with no meaningful security boundary may be
    `not_required`.

    Examples
    --------
    A current public API model covering assets, trust crossings, actors, abuse paths, mitigations,
    and accepted residual risks is `complete`. A model for an old architecture is `stale` or
    `misaligned` even when every document section exists.

    References
    ----------
    Cites "OWASP Threat Modeling Cheat Sheet"
    Cites "NIST Secure Software Development Framework"
    Cites "Microsoft Security Development Lifecycle", threat modeling
    """
    return backend.classification(
        subject,
        category=_ThreatModelCoverage,
        instructions=threat_model_coverage.instructions,
    )
