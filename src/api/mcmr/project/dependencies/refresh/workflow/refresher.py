from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING

import anyio
from patos import FrozenModel
from pydantic import Field, InstanceOf, PositiveInt

from .....domain.primitives import JsonTransport
from .....facts import DependencyFact, SourceSpan
from ...inventory import DependencyDeclaration, DependencyInventory
from ..simple import SimpleProject
from ..transport import UrlJsonTransport
from .client import DependencyClient
from .state import DependencyProgress, failure, latest_version

if TYPE_CHECKING:
    from .....facts import DependencyRecord, Evidence
    from ..release import ReleaseProject


class DependencyRefresher(FrozenModel):
    """Collect bounded objective upstream facts into MCMR's offline evidence contract."""

    root: Path
    transport: InstanceOf[JsonTransport] = Field(default_factory=UrlJsonTransport)
    workers: PositiveInt = 8

    async def collect(
        self,
        inventory: DependencyInventory,
        declaration: DependencyDeclaration,
        semaphore: anyio.Semaphore,
    ) -> tuple[DependencyRecord, list[Evidence]]:
        """Collect independent index, release, and repository facts for one declaration."""
        progress = self._resolution(inventory, declaration)
        await self._index(progress, declaration, semaphore)
        await self._releases(progress, declaration.name, semaphore)
        await self._repository(progress, declaration.name, semaphore)
        return progress.result

    async def refresh(self) -> DependencyFact:
        """Enrich every direct dependency concurrently and return one repository fact."""
        inventory = DependencyInventory(root=self.root)
        semaphore = anyio.Semaphore(self.workers)
        records: dict[str, DependencyRecord] = {}
        evidence: dict[str, Evidence] = {}

        async def collect(declaration: DependencyDeclaration) -> None:
            record, failures = await self.collect(inventory, declaration, semaphore)
            records[declaration.name] = record
            evidence.update((item.signal, item) for item in failures)

        async with anyio.create_task_group() as group:
            for declaration in inventory.declarations():
                group.start_soon(collect, declaration)
        return DependencyFact(
            key="dependencies",
            span=SourceSpan(path="pyproject.toml"),
            dependencies=[records[name] for name in sorted(records)],
            evidence=[evidence[name] for name in sorted(evidence)],
        )

    @cached_property
    def _client(self) -> DependencyClient:
        """Share the configured transport across bounded upstream requests."""
        return DependencyClient(transport=self.transport)

    @staticmethod
    def _latest_failure(name: str) -> Evidence:
        """Retain an index that offers no compatible release."""
        return failure(
            signal=f"dependency:{name}:latest-compatible-version",
            source=f"https://pypi.org/simple/{name}/",
            reason="no compatible PyPI release",
        )

    @staticmethod
    def _resolution_failures(
        declaration: DependencyDeclaration,
        reason: str | None,
    ) -> list[Evidence]:
        """Retain why one installed dependency could not be resolved."""
        if reason is None:
            return []
        return [
            failure(
                signal=f"dependency:{declaration.name}:resolved-version",
                source="installed-metadata",
                reason=reason,
            )
        ]

    async def _index(
        self,
        progress: DependencyProgress,
        declaration: DependencyDeclaration,
        semaphore: anyio.Semaphore,
    ) -> None:
        """Collect index state and the newest compatible version."""
        simple, index_failure = await self._simple_project(declaration.name, semaphore)
        latest = latest_version(simple.versions, declaration.requirement) if simple else None
        failures = [index_failure] if index_failure is not None else []
        if simple is not None and latest is None:
            failures.append(self._latest_failure(declaration.name))
        progress.accept_index(simple, latest, failures)

    async def _latest_release(
        self,
        name: str,
        version: str | None,
        semaphore: anyio.Semaphore,
    ) -> tuple[ReleaseProject | None, Evidence | None]:
        """Collect the newest compatible release."""
        return await self._client.release(name, version, "latest-compatible-release", semaphore)

    async def _releases(
        self,
        progress: DependencyProgress,
        name: str,
        semaphore: anyio.Semaphore,
    ) -> None:
        """Collect resolved and latest releases without requesting one version twice."""
        version = progress.resolved_version
        resolved, release_failure = await self._resolved_release(name, version, semaphore)
        failures = [release_failure] if release_failure is not None else []
        latest = resolved
        if resolved is None or progress.latest_version != progress.resolved_version:
            latest, release_failure = await self._latest_release(
                name, progress.latest_version, semaphore
            )
            failures += [release_failure] if release_failure is not None else []
        progress.accept_releases(resolved=resolved, latest=latest, failures=failures)

    async def _repository(
        self,
        progress: DependencyProgress,
        name: str,
        semaphore: anyio.Semaphore,
    ) -> None:
        """Collect the canonical source repository state."""
        state, repository_failure = await self._client.repository(
            name, progress.repository_urls, semaphore
        )
        failures = [repository_failure] if repository_failure is not None else []
        progress.accept_repository(state, failures)

    def _resolution(
        self,
        inventory: DependencyInventory,
        declaration: DependencyDeclaration,
    ) -> DependencyProgress:
        """Resolve one installed version and retain why it is unavailable."""
        resolution = inventory.resolved_version(
            name=declaration.name, requirement=declaration.requirement
        )
        failures = self._resolution_failures(declaration, resolution.failure)
        return DependencyProgress.start(declaration, resolution.version, failures)

    async def _resolved_release(
        self,
        name: str,
        version: str | None,
        semaphore: anyio.Semaphore,
    ) -> tuple[ReleaseProject | None, Evidence | None]:
        """Collect the exact installed release."""
        return await self._client.release(name, version, "resolved-release", semaphore)

    async def _simple_project(
        self,
        name: str,
        semaphore: anyio.Semaphore,
    ) -> tuple[SimpleProject | None, Evidence | None]:
        """Fetch one project from the PyPI simple index."""
        url = f"https://pypi.org/simple/{name}/"
        return await self._client.fetch(
            SimpleProject,
            url,
            signal=f"dependency:{name}:index",
            semaphore=semaphore,
            accept="application/vnd.pypi.simple.v1+json",
        )
