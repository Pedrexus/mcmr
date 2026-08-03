from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from .region import ExceptionRegion


class TryBlockFact(Fact):
    """Describe one try statement and its handlers."""

    regions: list[ExceptionRegion] = []
