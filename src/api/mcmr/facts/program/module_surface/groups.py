from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from pydantic import NonNegativeInt

    from .types import ModuleSurfaceTypes


class ModuleSurfaceFields(Fact):
    """Retain module exports and type-system surface evidence."""

    star_reexports: list[str] = []
    named_reexport_count: NonNegativeInt = 0
    export_count: NonNegativeInt = 0
    is_index_module: bool = False
    deepest_relative_import: NonNegativeInt = 0
    deepest_relative_specifier: str = ""
    erasable_violations: list[ModuleSurfaceTypes.ErasableConstruct] = []
