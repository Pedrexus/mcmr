from patos import FrozenModel

from .....facts import DependencyReleaseState
from .file import ReleaseFile
from .info import ReleaseInfo


class ReleaseProject(FrozenModel):
    """Relevant PyPI JSON metadata for one exact release."""

    info: ReleaseInfo
    urls: list[ReleaseFile]

    @property
    def first_upload_day(self) -> int:
        """Return the earliest exact artifact upload as a comparable ordinal day."""
        if not self.urls:
            raise ValueError("release has no artifacts")
        return min(item.upload_time_iso_8601 for item in self.urls).date().toordinal()

    @property
    def release_state(self) -> DependencyReleaseState:
        """Return exact yanking state or an explicit unknown state without artifacts."""
        if not self.urls:
            return DependencyReleaseState.UNKNOWN
        if all(item.yanked for item in self.urls):
            return DependencyReleaseState.YANKED
        return DependencyReleaseState.AVAILABLE
