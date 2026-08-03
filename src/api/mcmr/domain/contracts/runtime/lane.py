from enum import StrEnum, auto


class RuleLane(StrEnum):
    """Identify whether one rule computes or estimates its answer.

    A deterministic rule reads structure and gives the same answer twice. A contextual rule asks
    a classification backend chosen by the caller. The lane owns the leading digit of every rule
    number, which prevents deterministic and contextual rules from sharing one identifier.
    """

    DETERMINISTIC = auto()
    CONTEXTUAL = auto()

    @property
    def slot(self) -> str:
        """Return the digit every rule number in this lane begins with."""
        return "0" if self is RuleLane.DETERMINISTIC else "1"
