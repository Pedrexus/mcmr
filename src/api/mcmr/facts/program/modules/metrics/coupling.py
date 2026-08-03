from patos import FrozenModel
from pydantic import NonNegativeInt


class ModuleCoupling(FrozenModel):
    """Retain inward and outward internal module dependency counts."""

    module: str = ""
    afferent_count: NonNegativeInt = 0
    efferent_count: NonNegativeInt = 0

    @property
    def instability(self) -> float:
        """Return Martin's share of coupling that points outward."""
        total = self.afferent_count + self.efferent_count
        return self.efferent_count / total if total else 0.0
