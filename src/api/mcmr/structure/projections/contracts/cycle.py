from patos import FrozenModel


class Cycle(FrozenModel):
    """Hold modules that no dependency ordering can separate."""

    members: list[str]
