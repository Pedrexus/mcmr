from patos import FrozenModel

from ....domain.primitives import NonEmptyStr


class AuthorshipFields(FrozenModel):
    """Retain analyzer segment, provider, version, and rule."""

    segment: NonEmptyStr
    provider: NonEmptyStr
    provider_version: str = ""
    rule: str = ""
