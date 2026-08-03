from typing import TYPE_CHECKING

from pydantic import model_validator

from .groups import OverrideFields

if TYPE_CHECKING:
    from typing import Self

    from ..declarations.member import MemberDeclaration


class OverrideFact(OverrideFields):
    """Describe one inheritance link and how the subclass handles inherited members."""

    ancestor_names: list[str] = []
    declared: list[MemberDeclaration] = []
    inherited: list[MemberDeclaration] = []
    initializer_calls: list[str] = []

    @model_validator(mode="after")
    def names_each_member_once(self) -> Self:
        """Require each inheritance side to expose one effective binding per name."""
        for side, declarations in (("declared", self.declared), ("inherited", self.inherited)):
            names = [item.name for item in declarations]
            if len(names) != len(set(names)):
                raise ValueError(f"override link repeats a {side} member name")
        return self
