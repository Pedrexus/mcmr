from patos import FrozenModel

from ....domain.primitives import NonEmptyStr


class FailureScenario(FrozenModel):
    """Retain one failure concern and the concrete outcomes its tests assert."""

    name: NonEmptyStr
    source_paths: list[str] = []
    expected_outcomes: list[str] = []
    tests: list[str] = []
    asserted_outcomes: list[str] = []
    alternative_evidence: str = ""
