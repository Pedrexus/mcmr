from patos import FrozenModel

from ...facts import Fact


class FamilyPartition(FrozenModel):
    """Partition requested fact families by their provider boundary."""

    native: set[type[Fact]]
    external: set[type[Fact]]
