from typing import Literal

from patos import FrozenModel

from ...foundation import SymbolRef


class Symbol(FrozenModel):
    """Retain one declaration and its proven value contract."""

    name: str
    scope: Literal["module", "class", "local"]
    is_constant_assignment: bool = False
    returns_boolean: bool = False
    reference: SymbolRef | None = None
