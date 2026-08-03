from patos import FrozenModel

from ....domain.primitives import NonEmptyStr


class OperationalRisk(FrozenModel):
    """Retain one failure concern before contextual assessment."""

    name: NonEmptyStr
    critical_path: str = ""
    failure_modes: list[str] = []
    diagnostic_questions: list[str] = []
    signals: list[str] = []
    owner: str = ""
