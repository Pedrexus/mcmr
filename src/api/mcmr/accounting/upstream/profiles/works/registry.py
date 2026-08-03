from functools import cached_property
from importlib.resources import files

from patos import FrozenModel

from .work import Work


class WorkRegistry(FrozenModel):
    """Resolve every published work a rule reference may cite."""

    works: list[Work]

    @cached_property
    def by_title(self) -> dict[str, Work]:
        """Return every work keyed by the title a reference line quotes."""
        return {work.title: work for work in self.works}

    @classmethod
    def load(cls) -> WorkRegistry:
        """Read the registry of works this package ships."""
        source = files("mcmr.data").joinpath("works.json").read_text()
        return cls.model_validate_json(source)

    def of(self, title: str) -> Work | None:
        """Return the work a quoted title names, or nothing when none is registered."""
        return self.by_title.get(title)
