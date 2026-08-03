from patos import FrozenModel

from ...profiles.coverage import Coverage


class Gap(FrozenModel):
    """State why MCMR does not answer a set of one upstream tool's rules."""

    coverage: Coverage
    reason: str
    symbols: list[str] = []
    groups: list[str] = []
