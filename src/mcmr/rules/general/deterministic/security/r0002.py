from ..... import rule
from .....facts import SecurityBoundaryFact
from .....models import Percentage


@rule
def threat_model_coverage(
    subject: SecurityBoundaryFact,
) -> Percentage:
    """Measure security-sensitive boundaries covered by current threat analysis.

    Definition
    ----------
    Divide in-scope security-sensitive boundaries with assets, actors, threats, mitigations,
    residual risk, owner, and review evidence by all discovered boundaries and return the
    percentage.

    Evidence
    --------
    Findings retain boundary, assets, flows, actors, threats, mitigations, owner, and review date.
    The value is the percentage of discovered boundaries carrying complete threat analysis.

    Exceptions
    ----------
    Low-risk local components may inherit a reviewed parent threat model when coverage is explicit.

    Examples
    --------
    Eight analyzed boundaries among ten produce `80`. Listing threats without mitigations and an
    owner does not satisfy coverage.

    References
    ----------
    Cites "OWASP Threat Modeling Cheat Sheet"
    Cites "NIST Secure Software Development Framework"
    Cites "Microsoft Security Development Lifecycle", threat modeling
    """
    return subject.boundaries.coverage(
        "assets", "actors", "threats", "mitigations", "residual_risk", "owner", "review"
    )
