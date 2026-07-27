from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import AuthorityGrantFact


class LeastPrivilege(StrEnum):
    MINIMAL = auto()
    EXCESSIVE = auto()
    AMBIENT = auto()
    TEMPORARY = auto()
    UNCERTAIN = auto()


@rule
async def least_privilege(
    subject: AuthorityGrantFact,
    backend: ClassificationBackend,
) -> LeastPrivilege:
    """Judge whether code and services receive only necessary authority.

    Definition
    ----------
    Compare actual operations with filesystem, network, cloud, database, token, process, and user
    permissions. Consider scope, duration, delegation, separation, and emergency access.

    Evidence
    --------
    Findings cite operations, identities, grants, resources, observed use, duration, and ownership.

    Exceptions
    ----------
    Temporary emergency elevation may be justified when bounded, audited, and reviewed.

    Examples
    --------
    A read-only worker holding database administration rights is `excessive`. A deployment identity
    limited to one service and environment is `minimal`.

    References
    ----------
    Cites "The Protection of Information in Computer Systems", least privilege
    Cites "NIST Secure Software Development Framework"
    Cites "OpenSSF Scorecard", token permissions check
    """
    return await backend.classify(
        subject,
        category=LeastPrivilege,
        instructions=(
            "Compare actual operations with filesystem, network, cloud, database, token,"
            "process, and user permissions. Consider scope, duration, delegation,"
            "separation, and emergency access."
        ),
    )
