from typing import Literal

from patos import FrozenModel
from pydantic import NonNegativeInt


class LocalCollection(FrozenModel):
    """Retain one local collection and its representation-sensitive uses."""

    name: str = ""
    kind: Literal["list", "tuple"]
    value_count: NonNegativeInt
    has_homogeneous_literals: bool
    all_reads_are_iteration: bool = False
    all_reads_are_membership: bool = False
    values_are_unique: bool = False
