from typing import TYPE_CHECKING

from patos import FrozenModel
from pydantic import NonNegativeInt, PositiveInt

from ....primitives import NonEmptyStr

if TYPE_CHECKING:
    from typing import Self


class ModelProvenance(FrozenModel):
    """Identify the isolated model run that produced one contextual finding."""

    backend: NonEmptyStr
    model: NonEmptyStr
    reasoning_effort: NonEmptyStr
    input_tokens: NonNegativeInt = 0
    cached_input_tokens: NonNegativeInt = 0
    output_tokens: NonNegativeInt = 0
    reasoning_tokens: NonNegativeInt = 0

    def distribute(self, parts: PositiveInt) -> list[Self]:
        """Split one batch turn's token usage exactly across its candidate answers."""
        return [
            self.model_copy(
                update={
                    "input_tokens": self._share(self.input_tokens, parts, index),
                    "cached_input_tokens": self._share(self.cached_input_tokens, parts, index),
                    "output_tokens": self._share(self.output_tokens, parts, index),
                    "reasoning_tokens": self._share(self.reasoning_tokens, parts, index),
                }
            )
            for index in range(parts)
        ]

    @staticmethod
    def _share(value: int, parts: PositiveInt, index: int) -> int:
        """Assign one integer remainder deterministically without losing a token."""
        quotient, remainder = divmod(value, parts)
        return quotient + int(index < remainder)
