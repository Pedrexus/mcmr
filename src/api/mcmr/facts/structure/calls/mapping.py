from patos import FrozenModel

from .expression import Expression


class MappingEntry(FrozenModel):
    """Retain one key and value of a directly stated literal mapping."""

    key: str
    value: Expression
