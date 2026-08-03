from typing import TYPE_CHECKING

from .groups import FunctionFields
from .types import FunctionTypes

if TYPE_CHECKING:
    from typing import ClassVar


class FunctionFact(FunctionFields.Validation):
    """Describe one function or method and its resolved body facts."""

    ControlIncrement: ClassVar[type[FunctionTypes.ControlIncrement]] = (
        FunctionTypes.ControlIncrement
    )
    Parameter: ClassVar[type[FunctionTypes.Parameter]] = FunctionTypes.Parameter
