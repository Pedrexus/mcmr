from patos import FrozenModel

from .members import Member


class DiagramNode(FrozenModel):
    """Hold one diagram box under its repository-wide identity."""

    key: str
    label: str
    members: list[Member] = []
