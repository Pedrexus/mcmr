from patos import FrozenModel

from ....primitives import NonEmptyStr, Unit


class Measurement(FrozenModel):
    """Name one measured value that supports a finding."""

    name: NonEmptyStr
    value: float
    unit: Unit = Unit.COUNT

    @property
    def rendered(self) -> str:
        """Return this measurement as a compact reader-facing phrase."""
        amount = f"{self.value:.4g}%" if self.unit is Unit.PERCENTAGE else f"{self.value:.4g}"
        return f"{self.name} {amount}"
