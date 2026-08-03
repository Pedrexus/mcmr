from patos import FrozenModel


class AutomationTask(FrozenModel):
    """Describe one repository-owned command for a lifecycle capability."""

    capability: str
    commands: list[str] = []
    guidance_locations: list[str] = []
    is_repository_owned: bool = True
    is_noninteractive: bool = True
