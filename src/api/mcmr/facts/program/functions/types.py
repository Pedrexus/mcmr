from enum import StrEnum, auto

from patos import FrozenModel
from pydantic import NonNegativeInt


class FunctionTypes:
    """Name the structured records embedded in one function fact."""

    class ControlKind(StrEnum):
        """Name one control structure in language-neutral terms."""

        CONDITIONAL = auto()
        ALTERNATIVE = auto()
        LOOP = auto()
        SWITCH = auto()
        CATCH = auto()
        JUMP = auto()
        RECURSION = auto()
        SEQUENCE = auto()

    class ControlIncrement(FrozenModel):
        """Retain one control structure and its nesting depth."""

        kind: FunctionTypes.ControlKind
        nesting_depth: NonNegativeInt = 0

    class ParameterIdentity(FrozenModel):
        """Retain one parameter's name, type, and binding position."""

        name: str
        type_name: str = ""
        is_positional_only: bool = False
        is_keyword_only: bool = False

    class Parameter(ParameterIdentity):
        """Describe one resolved parameter and its call contract."""

        is_receiver: bool = False
        is_required_by_external_contract: bool = False
        has_boolean_annotation: bool = False
        has_boolean_default: bool = False


ControlKind = FunctionTypes.ControlKind
