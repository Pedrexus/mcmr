from typing import TYPE_CHECKING

from patos import FrozenModel
from pydantic import InstanceOf, JsonValue

from .....domain.primitives import JsonTransport
from .....facts import DependencyRepositoryState, Evidence
from ..release import ReleaseProject
from ..repository import GitHubRepository
from .state import failure, repository_name

if TYPE_CHECKING:
    from collections.abc import Mapping

    import anyio


class DependencyClient(FrozenModel):
    """Fetch and validate bounded dependency evidence from upstream services."""

    transport: InstanceOf[JsonTransport]

    async def fetch[Response: FrozenModel](
        self,
        response_type: type[Response],
        url: str,
        *,
        signal: str,
        semaphore: anyio.Semaphore,
        accept: str = "application/json",
    ) -> tuple[Response | None, Evidence | None]:
        """Fetch one model and turn bounded failures into retained evidence."""
        try:
            document = await self._document(url, accept=accept, semaphore=semaphore)
        except OSError as error:
            return None, failure(signal=signal, source=url, reason=type(error).__name__)
        return self._validated(response_type, document, signal=signal, source=url)

    async def release(
        self,
        name: str,
        version: str | None,
        field: str,
        semaphore: anyio.Semaphore,
    ) -> tuple[ReleaseProject | None, Evidence | None]:
        """Fetch one exact PyPI release or retain its missing resolution."""
        if version is None:
            return self._missing_release(name=name, field=field)
        url = f"https://pypi.org/pypi/{name}/{version}/json"
        signal = f"dependency:{name}:{field}"
        return await self.fetch(ReleaseProject, url, signal=signal, semaphore=semaphore)

    async def repository(
        self,
        name: str,
        project_urls: Mapping[str, str],
        semaphore: anyio.Semaphore,
    ) -> tuple[DependencyRepositoryState, Evidence | None]:
        """Fetch the archive state of the canonical GitHub project link."""
        repository = repository_name(project_urls)
        if not repository:
            return self._missing_repository(name)
        response, failure_value = await self._repository_response(
            name=name, repository=repository, semaphore=semaphore
        )
        state = self._repository_state(response) if response else DependencyRepositoryState.UNKNOWN
        return state, failure_value

    @staticmethod
    def _missing_release(*, name: str, field: str) -> tuple[None, Evidence]:
        """Retain one release whose installed version could not be resolved."""
        return None, failure(
            signal=f"dependency:{name}:{field}",
            source="installed-metadata",
            reason="version is unresolved",
        )

    @staticmethod
    def _missing_repository(name: str) -> tuple[DependencyRepositoryState, Evidence]:
        """Retain one release that publishes no canonical GitHub project."""
        return DependencyRepositoryState.UNKNOWN, failure(
            signal=f"dependency:{name}:repository-state",
            source="pypi-release",
            reason="GitHub repository is not published",
        )

    @staticmethod
    def _repository_state(repository: GitHubRepository) -> DependencyRepositoryState:
        """Translate the GitHub archive flag into the closed state."""
        return (
            DependencyRepositoryState.ARCHIVED
            if repository.archived
            else DependencyRepositoryState.ACTIVE
        )

    @staticmethod
    def _validated[Response: FrozenModel](
        response_type: type[Response],
        document: JsonValue,
        *,
        signal: str,
        source: str,
    ) -> tuple[Response | None, Evidence | None]:
        """Validate one response and retain a bounded failure."""
        try:
            return response_type.model_validate(document, extra="ignore"), None
        except ValueError as error:
            return None, failure(signal=signal, source=source, reason=type(error).__name__)

    async def _document(
        self,
        url: str,
        *,
        accept: str,
        semaphore: anyio.Semaphore,
    ) -> JsonValue:
        """Fetch one document under the shared concurrency bound."""
        async with semaphore:
            return await self.transport.get(url, accept=accept)

    async def _repository_response(
        self,
        *,
        name: str,
        repository: str,
        semaphore: anyio.Semaphore,
    ) -> tuple[GitHubRepository | None, Evidence | None]:
        """Fetch one canonical GitHub repository response."""
        return await self.fetch(
            GitHubRepository,
            f"https://api.github.com/repos/{repository}",
            signal=f"dependency:{name}:repository-state",
            semaphore=semaphore,
        )
