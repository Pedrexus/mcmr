from patos import FrozenModel
from pydantic import NonNegativeInt

from ....primitives import NonEmptyStr


class ModelProvenance(FrozenModel):
    """Identify the isolated model run that produced one contextual finding."""

    backend: NonEmptyStr
    model: NonEmptyStr
    reasoning_effort: NonEmptyStr
    input_tokens: NonNegativeInt = 0
    cached_input_tokens: NonNegativeInt = 0
    output_tokens: NonNegativeInt = 0
    reasoning_tokens: NonNegativeInt = 0
