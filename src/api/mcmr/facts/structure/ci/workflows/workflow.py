from patos import FrozenModel


class CIWorkflow(FrozenModel):
    """Describe one parsed workflow and its protections."""

    name: str
    tasks: list[str] = []
    triggers: list[str] = []
    is_change_blocking: bool = False
    uses_locked_dependencies: bool = True
    has_explicit_permissions: bool = True
    cancels_superseded_runs: bool = True
