from patos import FrozenModel

from ....domain.primitives import NonEmptyStr


class ArchitectureFields(FrozenModel):
    """Retain architecture quality name, objective, check, and result."""

    name: NonEmptyStr
    objective: str = ""
    check: str = ""
    retained_result: str = ""
