from patos import FrozenModel
from pydantic import NonNegativeInt


class PairSequence(FrozenModel):
    """Retain one literal pair sequence and its lookup-only reads."""

    pair_count: NonNegativeInt
    keys_are_unique_literals: bool
    has_single_assignment: bool
    all_reads_are_lookup_loops: bool
