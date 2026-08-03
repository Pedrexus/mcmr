from typing import TYPE_CHECKING

from patos import FrozenModel
from pydantic import model_validator

from .definition import TypingDefinition
from .reuse import TypingReuse

if TYPE_CHECKING:
    from typing import Self


class TypingScope(FrozenModel):
    """Retain type declarations and resolved reuse inside one cohesive directory."""

    path: str
    definitions: list[TypingDefinition] = []
    reused_definitions: list[TypingReuse] = []

    @model_validator(mode="after")
    def reuse_refers_to_declared_types(self) -> Self:
        """Require unique declarations and reuse records from this exact scope."""
        declared = [(item.name, item.span.path) for item in self.definitions]
        reused = [(item.name, item.span.path) for item in self.reused_definitions]
        if len(declared) != len(set(declared)):
            raise ValueError("typing scope repeats a declaration")
        if len(reused) != len(set(reused)):
            raise ValueError("typing scope repeats a reused declaration")
        if not set(reused).issubset(declared):
            raise ValueError("typing scope reuses a declaration it does not hold")
        return self
