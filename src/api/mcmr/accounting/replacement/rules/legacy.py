from patos import FrozenModel

from ....domain.primitives import NonEmptyStr


class LegacyRule(FrozenModel):
    """Freeze one rule from the final GE4M catalog independently of its implementation."""

    id: NonEmptyStr
    summary: NonEmptyStr
    backend: NonEmptyStr
