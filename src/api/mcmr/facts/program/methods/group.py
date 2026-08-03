from patos import FrozenModel


class MethodCloneGroup(FrozenModel):
    """Retain exact sibling method definitions sharing a meaningful base."""

    normalized_definition: str
    locations: list[str] = []
    direct_base: str
