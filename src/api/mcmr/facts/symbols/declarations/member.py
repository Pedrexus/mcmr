from patos import FrozenModel
from pydantic import PositiveInt

from .parameter import ParameterDeclaration


class MemberDeclaration(FrozenModel):
    """Retain a member exactly as its owning class writes it down."""

    name: str = ""
    parameters: list[ParameterDeclaration] | None = None
    decorators: list[str] = []
    asynchronous: bool = False
    line: PositiveInt = 1
    source: str = ""
