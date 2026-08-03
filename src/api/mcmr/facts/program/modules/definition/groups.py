from typing import TYPE_CHECKING

from ....foundation import Fact

if TYPE_CHECKING:
    from pydantic import NonNegativeInt

    from .constant import ConstantPlacement


class ModuleFields(Fact):
    """Retain module size, declaration, and package identity fields."""

    constant_placements: list[ConstantPlacement] = []
    physical_line_count: NonNegativeInt = 0
    statement_count: NonNegativeInt = 0
    class_count: NonNegativeInt = 0
    function_count: NonNegativeInt = 0
    executable_statement_count: NonNegativeInt = 0
    is_package_initializer: bool = False
