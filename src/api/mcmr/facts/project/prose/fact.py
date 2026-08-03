from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from .section import ProseSection


class ProseSegmentFact(Fact):
    """Describe one coherent prose segment from source or documentation."""

    sections: list[ProseSection] = []
