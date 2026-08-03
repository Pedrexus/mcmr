from patos import FrozenModel

from .kind import ParameterKind


class ParameterDeclaration(FrozenModel):
    """Retain a parameter exactly as its declaration writes it down."""

    name: str = ""
    kind: ParameterKind = ParameterKind.POSITIONAL_OR_KEYWORD
    has_default: bool = False
