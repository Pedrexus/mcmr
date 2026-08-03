import importlib
from functools import cached_property
from importlib import metadata, resources
from types import ModuleType
from typing import TYPE_CHECKING

from patos import FrozenModel

if TYPE_CHECKING:
    from importlib.resources.abc import Traversable


class RuleModuleDiscovery(FrozenModel):
    """Import built-in and installed plugin rule modules in stable path order."""

    package: str = "mcmr.rules"
    plugin_group: str = "mcmr.rules"
    include_plugins: bool = True

    @cached_property
    def modules(self) -> list[ModuleType]:
        """Return imported leaf modules that can contain rule declarations."""
        roots = [importlib.import_module(self.package)]
        if self.include_plugins:
            for entry in sorted(
                metadata.entry_points(group=self.plugin_group),
                key=lambda item: (item.name, item.value),
            ):
                loaded = entry.load()
                if not isinstance(loaded, ModuleType):
                    raise TypeError(f"MCMR rule plugin {entry.name} must load a module or package")
                roots.append(loaded)
        modules = {module.__name__: module for root in roots for module in self.leaves(root)}
        return [modules[name] for name in sorted(modules)]

    @classmethod
    def leaves(cls, root: ModuleType) -> list[ModuleType]:
        """Return one module or every importable leaf below one package."""
        path = getattr(root, "__path__", None)
        if path is None:
            return [root]
        names = sorted(cls.module_names(resources.files(root), root.__name__))
        return [importlib.import_module(name) for name in names]

    @classmethod
    def module_names(cls, directory: Traversable, package: str) -> list[str]:
        """Return source module names below one resource tree, including namespace directories."""
        found: list[str] = []
        for entry in directory.iterdir():
            if entry.name == "__pycache__":
                continue
            if entry.is_dir():
                found.extend(cls.module_names(entry, f"{package}.{entry.name}"))
            elif entry.name.endswith(".py") and entry.name != "__init__.py":
                found.append(f"{package}.{entry.name.removesuffix('.py')}")
        return found
