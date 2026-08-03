from typing import TYPE_CHECKING
from urllib.parse import urlparse

from packaging.requirements import Requirement
from packaging.version import Version
from patos import Model
from pydantic import Field

from .....facts import (
    DependencyProjectState,
    DependencyRecord,
    DependencyReleaseState,
    DependencyRepositoryState,
    Evidence,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from pydantic import JsonValue

    from ...inventory import DependencyDeclaration
    from ..release import ReleaseProject
    from ..simple import SimpleProject


class DependencyProgress(Model):
    """Carry one dependency through its independent upstream lookups."""

    record: DependencyRecord
    resolved_version: str | None = Field(default=None, min_length=1)
    latest_version: str | None = Field(default=None, min_length=1)
    repository_urls: dict[str, str] = {}
    failures: list[Evidence] = []

    @property
    def result(self) -> tuple[DependencyRecord, list[Evidence]]:
        """Return the completed record and retained unknown evidence."""
        return self.record, self.failures

    @classmethod
    def start(
        cls,
        declaration: DependencyDeclaration,
        version: str | None,
        failures: list[Evidence],
    ) -> DependencyProgress:
        """Start one dependency from its local declaration and resolution."""
        record = DependencyRecord(
            name=declaration.name,
            is_development=declaration.is_development,
        )
        return cls(record=record, resolved_version=version, failures=failures)

    def accept_index(
        self,
        project: SimpleProject | None,
        latest_version: str | None,
        failures: list[Evidence],
    ) -> None:
        """Merge normalized simple index evidence."""
        updates = {
            "latest_compatible_version": latest_version,
            "project_state": project_state(project),
        }
        self.latest_version = latest_version
        self.record = self.record.model_copy(update=updates)
        self.failures.extend(failures)

    def accept_releases(
        self,
        *,
        resolved: ReleaseProject | None,
        latest: ReleaseProject | None,
        failures: list[Evidence],
    ) -> None:
        """Merge normalized exact and compatible release evidence."""
        self.repository_urls = resolved.info.project_urls if resolved else {}
        self.record = self.record.model_copy(
            update=self._release_fields(resolved=resolved, latest=latest)
        )
        self.failures.extend(failures)

    def accept_repository(
        self,
        state: DependencyRepositoryState,
        failures: list[Evidence],
    ) -> None:
        """Merge normalized source repository evidence."""
        self.record = self.record.model_copy(update={"repository_state": state})
        self.failures.extend(failures)

    @staticmethod
    def _release_fields(
        *,
        resolved: ReleaseProject | None,
        latest: ReleaseProject | None,
    ) -> dict[str, JsonValue]:
        """Return record values owned by exact release lookups."""
        return {
            "resolved_release_day": resolved.first_upload_day if resolved else None,
            "latest_compatible_release_day": latest.first_upload_day if latest else None,
            "resolved_release_state": (
                resolved.release_state if resolved else DependencyReleaseState.UNKNOWN
            ),
        }


def failure(*, signal: str, source: str, reason: str) -> Evidence:
    """Retain one stable unknown fact without leaking a transport diagnostic."""
    field = signal.rsplit(":", 1)[-1]
    return Evidence(
        signal=signal,
        detail=f"{field} is unknown because {reason}",
        source=source,
    )


def latest_version(versions: Sequence[str], requirement: str) -> str | None:
    """Return the greatest valid PEP 440 release allowed by one requirement."""
    specifier = Requirement(requirement).specifier
    compatible = list(specifier.filter(Version(value) for value in versions))
    return str(max(compatible)) if compatible else None


def project_state(project: SimpleProject | None) -> DependencyProjectState:
    """Return one standardized PyPI project state."""
    if project is None:
        return DependencyProjectState.UNKNOWN
    try:
        return DependencyProjectState(project.project_status.get("status", "unknown"))
    except ValueError:
        return DependencyProjectState.UNKNOWN


def repository_name(project_urls: Mapping[str, str]) -> str:
    """Return the preferred canonical GitHub owner and repository."""
    return next(filter(None, map(_github_name, _urls(project_urls))), "")


def _github_name(url: str) -> str:
    """Return a canonical GitHub owner and repository when one URL names it."""
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    return (
        f"{parts[0]}/{parts[1].removesuffix('.git')}"
        if parsed.hostname == "github.com" and len(parts) >= 2
        else ""
    )


def _urls(project_urls: Mapping[str, str]) -> list[str]:
    """Order project links by how directly their labels identify source."""
    priorities = {"source": 0, "repository": 1, "code": 2, "homepage": 3}
    ordered = sorted(project_urls.items(), key=lambda item: priorities.get(item[0].casefold(), 4))
    return [url for _, url in ordered]
