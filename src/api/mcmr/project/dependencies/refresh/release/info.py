from patos import FrozenModel
from pydantic import Field


class ReleaseInfo(FrozenModel):
    """Relevant project links published for one exact release."""

    project_urls: dict[str, str] = Field(default_factory=dict)
