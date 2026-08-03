from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from pydantic import NonNegativeInt, PositiveInt

    pass


class OverrideFields(Fact):
    """Retain override endpoints, depth, counts, decorators, and base names."""

    derived: str = ""
    base: str = ""
    depth: PositiveInt = 1
    overridden_member_count: NonNegativeInt = 0
    derived_decorators: list[str] = []
    base_decorators: list[str] = []
    base_names: list[str] = []
