from patos import FrozenModel

from .....facts import Visibility
from ...kinds import MemberKind


class Member(FrozenModel):
    """Hold one class member with its UML compartment and visibility."""

    name: str
    kind: MemberKind
    visibility: Visibility

    @property
    def marker(self) -> str:
        """Return the UML visibility sigil."""
        match self.visibility:
            case Visibility.PUBLIC:
                return "+"
            case Visibility.PRIVATE:
                return "-"
            case _:
                return "#"

    def signature(self) -> str:
        """Return the UML member signature."""
        return f"{self.name}()" if self.kind is MemberKind.METHOD else self.name
