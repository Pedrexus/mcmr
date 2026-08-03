from patos import FrozenModel
from pydantic import Field


class SimpleProject(FrozenModel):
    """Relevant PyPI Simple JSON metadata for one project."""

    versions: list[str] = []
    project_status: dict[str, str] = Field(default_factory=dict, validation_alias="project-status")
