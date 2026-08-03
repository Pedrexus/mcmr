from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from .access import AttributeAccess


class AttributeAccessFact(Fact):
    """Describe one resolved attribute access and its owning scope."""

    accesses: list[AttributeAccess] = []
