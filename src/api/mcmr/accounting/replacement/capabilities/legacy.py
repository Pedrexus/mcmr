from patos import FrozenModel

from ....domain.primitives import NonEmptyStr


class LegacyCapability(FrozenModel):
    """Freeze one externally meaningful GE4M behavior."""

    id: NonEmptyStr
    summary: NonEmptyStr
