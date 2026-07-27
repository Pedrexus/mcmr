from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import ReleaseFact


class ReleaseTraceability(StrEnum):
    TRACEABLE = auto()
    PARTIAL = auto()
    AMBIGUOUS = auto()
    UNRELEASED = auto()
    UNCERTAIN = auto()


@rule
async def release_traceability(
    subject: ReleaseFact,
    backend: ClassificationBackend,
) -> ReleaseTraceability:
    """Judge whether a release can be traced through its complete identity.

    Definition
    ----------
    Link version, source revision, dependency resolution, build invocation, artifact digest,
    provenance, change record, environment, and deployment outcome.

    Evidence
    --------
    Findings cite release metadata, source, lock state, build records, artifacts, and deployments.

    Exceptions
    ----------
    Unreleased applications may use immutable deployment identities instead of public versions.

    Examples
    --------
    A signed artifact linked to one revision, lockfile, build, and deployment is `traceable`.
    Reusing one mutable version for different artifacts is `ambiguous`.

    References
    ----------
    Cites "Site Reliability Engineering", Release Engineering
    Cites "SLSA specification"
    Cites "The Pragmatic Programmer", version control and automation
    """
    return await backend.classify(
        subject,
        category=ReleaseTraceability,
        instructions=(
            "Link version, source revision, dependency resolution, build invocation,"
            "artifact digest, provenance, change record, environment, and deployment"
            "outcome."
        ),
    )
