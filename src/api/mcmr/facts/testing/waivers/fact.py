from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from .waiver import Waiver


class WaiverFact(Fact):
    """Describe one rule waiver and its retained justification."""

    waivers: list[Waiver] = []
