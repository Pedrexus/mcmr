from patos import FrozenModel
from pydantic import NonNegativeInt

from .....domain.primitives import NonEmptyStr
from ..states.project import DependencyProjectState
from ..states.release import DependencyReleaseState
from ..states.repository import DependencyRepositoryState


class DependencyRecordFields(FrozenModel):
    """Retain release identity, dates, version, and standardized states."""

    name: NonEmptyStr
    resolved_release_day: NonNegativeInt | None = None
    latest_compatible_release_day: NonNegativeInt | None = None
    latest_compatible_version: NonEmptyStr | None = None
    project_state: DependencyProjectState = DependencyProjectState.UNKNOWN
    repository_state: DependencyRepositoryState = DependencyRepositoryState.UNKNOWN
    resolved_release_state: DependencyReleaseState = DependencyReleaseState.UNKNOWN
