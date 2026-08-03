from patos import FrozenModel


class Relation(FrozenModel):
    """Relate two named units in one repository vocabulary."""

    source: str
    target: str
