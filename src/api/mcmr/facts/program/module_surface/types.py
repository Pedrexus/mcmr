from typing import Literal

from patos import FrozenModel
from pydantic import PositiveInt


class ModuleSurfaceTypes:
    """Own the compact value models nested under one module surface fact."""

    class ErasableConstruct(FrozenModel):
        """Retain one construct surviving type stripping."""

        kind: Literal["enum", "const_enum", "namespace", "parameter_property", "import_equals"]
        name: str = ""
        line: PositiveInt = 1

    class EscapeHatch(FrozenModel):
        """Retain one place stepping around proven type information."""

        kind: Literal["assertion", "non_null", "any", "ignore_comment"]
        line: PositiveInt = 1
