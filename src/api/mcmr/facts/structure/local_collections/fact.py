from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from .local import LocalCollection
    from .pairs import PairSequence


class CollectionFact(Fact):
    """Describe one collection expression and its uses."""

    pair_sequences: list[PairSequence] = []
    local_collections: list[LocalCollection] = []
