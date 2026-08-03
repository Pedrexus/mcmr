from enum import StrEnum, auto

from .coverage import Coverage


class Relation(StrEnum):
    """Say how one MCMR rule stands to the upstream rule its reference names."""

    GENERALIZES = auto()
    ADAPTS = auto()
    CITES = auto()

    @property
    def coverage(self) -> Coverage | None:
        """Return the coverage this relation claims, or nothing when it claims none."""
        return {
            Relation.GENERALIZES: Coverage.NATIVE,
            Relation.ADAPTS: Coverage.ADAPTED,
        }.get(self)

    @property
    def word(self) -> str:
        """Return the word that opens a reference stating this relation."""
        return self.capitalize()
