from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from .characteristic import ArchitectureCharacteristic


class ArchitectureCharacteristicFact(Fact):
    """Describe one declared architecture characteristic and its evidence."""

    characteristics: list[ArchitectureCharacteristic] = []
