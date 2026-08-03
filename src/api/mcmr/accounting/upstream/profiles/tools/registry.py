from functools import cached_property
from importlib.resources import files

from patos import FrozenModel
from pydantic import Field, TypeAdapter

from .profile import ToolProfile


def _shipped_profiles() -> list[ToolProfile]:
    """Read the typed upstream tool profiles this package ships."""
    source = files("mcmr.data").joinpath("tools.json").read_text()
    return TypeAdapter(list[ToolProfile]).validate_json(source)


class ToolRegistry(FrozenModel):
    """Resolve every checker a rule reference may cite."""

    profiles: list[ToolProfile] = Field(default_factory=_shipped_profiles)

    @cached_property
    def by_name(self) -> dict[str, ToolProfile]:
        """Return every profile keyed by the lowercased name a docstring writes."""
        return {profile.name.casefold(): profile for profile in self.profiles}

    def of(self, name: str) -> ToolProfile | None:
        """Return the profile a token names, or nothing when no registered tool matches."""
        return self.by_name.get(name.casefold())
