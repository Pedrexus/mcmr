from patos import FrozenModel

from .....domain.primitives import NonEmptyStr


class SecurityBoundaryFields(FrozenModel):
    """Retain boundary identity, scope, assets, flows, actors, threats, and mitigations."""

    name: NonEmptyStr
    in_scope: bool = True
    assets: list[str] = []
    flows: list[str] = []
    actors: list[str] = []
    threats: list[str] = []
    mitigations: list[str] = []
