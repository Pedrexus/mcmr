from typing import Literal

from ..... import rule
from .....facts import DeploymentFact


@rule
def deployment_reproducibility(
    subject: DeploymentFact, *, require_provenance: bool = True
) -> Literal["reproducible", "partial", "nonreproducible", "not_applicable"]:
    """Assess whether deployment can reproduce one known artifact.

    Definition
    ----------
    Read the deployment record and ask whether each of the checks that make a deployment repeatable
    is present, which are locked inputs, a stated build command, a stated environment, an artifact
    identity, migrations, configuration, a secrets boundary, a rollback path, and provenance when
    `require_provenance` asks for it. All of them present is `reproducible`, some of them is
    `partial`, and none of them is `nonreproducible`.

    The point is not ceremony. A deployment nobody can reproduce is one nobody can roll back to, so
    the moment an incident asks what was actually running, the answer has to be reconstructed from
    memory. A project with no deployment target at all answers `not_applicable`, since a library
    shipped as source has nothing to reproduce.

    Evidence
    --------
    The finding retains every captured input and every step of the deployment the record does not
    cover. The value is the category, one of `reproducible`, `partial`, `nonreproducible`, and
    `not_applicable`.

    Exceptions
    ----------
    A project the record marks as having no deployment target returns `not_applicable` rather than
    failing, so a library is never judged against a service's checklist. Provenance is required
    only when `require_provenance` says so, since a project may attest to its artifacts outside the
    repository. Nothing here inspects a running system, so a record that claims a check is present
    is taken at its word and the rule measures the record rather than the deployment.

    Examples
    --------
    A content-addressed image built from locked inputs, with migrations, configuration, a secrets
    boundary, rollback, and provenance all recorded, returns `reproducible`. The same record
    without rollback returns `partial`. A deployment whose record captures none of the checks, such
    as one performed by editing a live server, returns `nonreproducible`. A library with no
    deployment target returns `not_applicable`.

    References
    ----------
    Cites "Reproducible Builds documentation"
    Cites "SLSA specification"
    Cites "The Twelve-Factor App"
    """
    if not subject.is_applicable:
        return "not_applicable"
    required = {
        "locked_inputs",
        "build_command",
        "environment",
        "artifact_identity",
        "migrations",
        "configuration",
        "secrets_boundary",
        "rollback",
        *({"provenance"} if require_provenance else set()),
    }
    present = sum(subject.reproducibility_checks.get(check, False) for check in required)
    if present == len(required):
        return "reproducible"
    return "partial" if present else "nonreproducible"
