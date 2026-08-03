from statistics import fmean
from typing import Annotated

from patos import FrozenModel
from pydantic import BeforeValidator, PositiveInt


class LengthDistribution(FrozenModel):
    """Provide derived statistics for one measured length distribution."""

    root: list[PositiveInt]

    def __len__(self) -> int:
        """Return the number of measured values."""
        return len(self.root)

    @classmethod
    def from_value(cls, value: LengthDistribution | list[int]) -> LengthDistribution:
        """Accept an existing distribution or validate one concise integer list."""
        if isinstance(value, list):
            return cls(root=value)
        return value

    def at_least(self, minimum: int) -> LengthDistribution:
        """Return values meeting one inclusive measurement floor."""
        return LengthDistribution(root=[value for value in self.root if value >= minimum])

    def uniformity(self) -> float:
        """Return inverse normalized mean absolute deviation as a percentage."""
        if not self.root:
            return 0.0
        mean = fmean(self.root)
        deviation = fmean(abs(value - mean) for value in self.root)
        return max(0.0, 1.0 - deviation / mean) * 100.0


type LengthDistributionValue = Annotated[
    LengthDistribution,
    BeforeValidator(LengthDistribution.from_value),
]
