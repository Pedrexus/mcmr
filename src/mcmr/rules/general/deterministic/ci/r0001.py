from typing import Literal

from ..... import rule
from .....facts import CIConfigurationFact


@rule
def continuous_integration(
    subject: CIConfigurationFact,
    *,
    required_tasks: tuple[str, ...] = ("lint", "typecheck", "test"),
) -> Literal["complete", "partial", "fragile", "absent"]:
    """Assess whether continuous integration enforces required gates.

    Definition
    ----------
    Inspect workflow triggers, required tasks, supported runtimes, dependency locking,
    cancellation, permissions, and branch protection in an explicit `.ge4m/ci.json` artifact. The
    engine skips the rule when that optional evidence is absent because a missing local artifact
    does not prove that the repository has no continuous integration.

    Evidence
    --------
    Findings retain workflows, triggers, commands, environments, and missing gates.

    Exceptions
    ----------
    A pre-release prototype can accept partial automation through explicit project policy. An
    explicit artifact with no gates classifies CI as absent. No artifact leaves the rule
    unassessed. `required_tasks` names the gates a change has to pass, defaulting to lint,
    typecheck, and test, so a project that spells its gates differently states its own.

    Examples
    --------
    A pull request workflow running lint, types, and tests is `complete` for those gates. A
    manually triggered test workflow is `partial` protection.

    References
    ----------
    Cites "Software Engineering at Google", Continuous Integration
    Cites "GitHub Actions documentation"
    Cites "OpenSSF Scorecard", CI tests
    """
    blocking = [workflow for workflow in subject.workflows if workflow.is_change_blocking]
    protected = {task for workflow in blocking for task in workflow.tasks}
    present = protected.intersection(required_tasks)
    if not present:
        return "absent"
    if present != set(required_tasks):
        return "partial"
    robust = all(
        workflow.uses_locked_dependencies
        and workflow.has_explicit_permissions
        and workflow.cancels_superseded_runs
        for workflow in blocking
        if set(workflow.tasks).intersection(required_tasks)
    )
    return "complete" if robust else "fragile"
