from patos import FrozenModel

from ....primitives import NonEmptyStr


class Criterion(FrozenModel):
    """Name one contextual predicate a model may estimate without choosing policy."""

    name: NonEmptyStr
    question: NonEmptyStr
