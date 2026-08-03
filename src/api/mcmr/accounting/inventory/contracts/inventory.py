from importlib.resources import files

from patos import FrozenModel

from .rule import ToolRule


class Inventory(FrozenModel):
    """Hold every rule one upstream tool ships, frozen from its own registry."""

    tool: str
    version: str
    rules: list[ToolRule]

    @classmethod
    def load(cls, tool: str) -> Inventory:
        """Read the inventory this package freezes for one tool."""
        source = files("mcmr.data").joinpath(f"{tool}.json").read_text()
        return cls.model_validate_json(source)
