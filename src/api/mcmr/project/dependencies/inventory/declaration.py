from patos import FrozenModel

from ....domain.primitives import NonEmptyStr


class DependencyDeclaration(FrozenModel):
    """Retain one direct Python requirement and whether it is development-only."""

    name: NonEmptyStr
    requirement: NonEmptyStr
    is_development: bool = False
