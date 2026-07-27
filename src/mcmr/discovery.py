import importlib
import pkgutil
from functools import cached_property
from typing import TYPE_CHECKING

from .bases import FrozenFlexModel

if TYPE_CHECKING:
    from types import ModuleType


class RuleModuleDiscovery(FrozenFlexModel):
    """Import every module beneath one rule package in stable path order."""

    package: str = "mcmr.rules"

    @cached_property
    def modules(self) -> list[ModuleType]:
        """Return imported leaf modules that can contain rule declarations."""
        package = importlib.import_module(self.package)
        names = sorted(
            item.name
            for item in pkgutil.walk_packages(package.__path__, prefix=f"{self.package}.")
            if not item.ispkg
        )
        return [importlib.import_module(name) for name in names]
