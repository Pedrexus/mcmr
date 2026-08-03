from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from .mechanism import InteropMechanism
    from .reference import InteropReference


class InteropFact(Fact):
    """Describe an artifact declared in one language and reached from another."""

    name: str
    mechanism: InteropMechanism
    declared_language: str
    references: list[InteropReference] = []
