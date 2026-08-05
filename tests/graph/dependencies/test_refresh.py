import importlib.metadata
import json
from datetime import date
from typing import TYPE_CHECKING

import anyio
import pytest
from packaging.version import InvalidVersion
from pydantic import ValidationError

from mcmr.execution.providers import DependencyProvider
from mcmr.facts import DependencyReleaseState, DependencyRepositoryState, Evidence
from mcmr.project.dependencies import (
    DependencyClient,
    DependencyResolution,
    ReleaseInfo,
    ReleaseProject,
    SimpleProject,
    latest_version,
    project_state,
    repository_name,
)

from .support import StubTransport, complete_refresh

if TYPE_CHECKING:
    from pathlib import Path


def test_refresh_builds_complete_dependency_facts_in_memory(tmp_path: Path) -> None:
    fact, transport = complete_refresh(tmp_path)
    record = fact.dependencies[0]

    assert (fact.evidence, fact.span.path, len(fact.dependencies)) == ([], "pyproject.toml", 1)
    assert (
        record.name,
        record.resolved_release_day,
        record.latest_compatible_release_day,
        record.latest_compatible_version,
        record.project_state,
        record.repository_state,
        record.resolved_release_state,
    ) == (
        "demo",
        date.fromisoformat("2024-01-02").toordinal(),
        date.fromisoformat("2025-01-03").toordinal(),
        "2.0",
        "active",
        DependencyRepositoryState.ARCHIVED,
        DependencyReleaseState.AVAILABLE,
    )
    assert transport.calls[0] == (
        "https://pypi.org/simple/demo/",
        "application/vnd.pypi.simple.v1+json",
    )


def test_refresh_retains_unknowns_and_does_not_turn_transport_failures_into_health(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\ndependencies = ['Missing>=1']\n")

    def missing(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", missing)
    simple = "https://pypi.org/simple/missing/"
    transport = StubTransport({simple: OSError("offline")})
    fact = anyio.run(DependencyProvider(root=tmp_path, transport=transport).refresh)
    record = fact.dependencies[0]

    assert (
        record.resolved_release_day,
        record.latest_compatible_release_day,
        record.latest_compatible_version,
        record.project_state,
        record.repository_state,
        record.resolved_release_state,
    ) == (
        None,
        None,
        None,
        "unknown",
        DependencyRepositoryState.UNKNOWN,
        DependencyReleaseState.UNKNOWN,
    )
    assert {item.signal for item in fact.evidence} == {
        "dependency:missing:index",
        "dependency:missing:latest-compatible-release",
        "dependency:missing:repository-state",
        "dependency:missing:resolved-release",
        "dependency:missing:resolved-version",
    }
    assert all("offline" not in item.detail for item in fact.evidence)


def test_refresh_retains_a_successful_index_with_no_compatible_release_as_a_gap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\ndependencies = ['Gap>=2']\n")

    def missing(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", missing)
    simple = "https://pypi.org/simple/gap/"
    fact = anyio.run(
        DependencyProvider(
            root=tmp_path,
            transport=StubTransport(
                {simple: {"versions": ["1.0"], "project-status": {"status": "active"}}}
            ),
        ).refresh
    )

    assert fact.dependencies[0].project_state == "active"
    assert "dependency:gap:latest-compatible-version" in {item.signal for item in fact.evidence}


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("active", "active"),
        ("archived", "archived"),
        ("deprecated", "deprecated"),
        ("quarantined", "quarantined"),
        ("invented", "unknown"),
    ],
)
def test_project_status_accepts_only_the_standardized_closed_states(
    *,
    status: str,
    expected: str,
) -> None:
    project = SimpleProject.model_validate_json(
        json.dumps({"versions": [], "project-status": {"status": status}})
    )
    assert project_state(project) == expected
    assert project_state(None) == "unknown"


def test_release_helpers_preserve_unknown_states() -> None:
    empty = ReleaseProject(info=ReleaseInfo(), urls=())
    assert empty.release_state is DependencyReleaseState.UNKNOWN
    with pytest.raises(ValueError, match="no artifacts"):
        _ = empty.first_upload_day

    assert latest_version(("1.0",), "demo>=2") is None
    with pytest.raises(InvalidVersion):
        latest_version(("bad",), "demo>=2")


def test_repository_names_prefer_the_named_repository_url() -> None:
    assert repository_name({"Docs": "https://example.com/docs"}) == ""
    assert (
        repository_name(
            {
                "Docs": "https://github.com/acme/secondary",
                "Repository": "https://github.com/acme/preferred.git/issues",
            }
        )
        == "acme/preferred"
    )


def test_dependency_resolution_requires_exactly_one_outcome() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        DependencyResolution()
    with pytest.raises(ValidationError, match="exactly one"):
        DependencyResolution(version="1.0", failure="failed")


def test_repository_validation_failure_is_retained_as_unknown_evidence() -> None:
    """Malformed remote JSON cannot become a healthy repository state."""
    url = "https://api.github.com/repos/acme/demo"
    client = DependencyClient(transport=StubTransport({url: {"archived": "not a Boolean"}}))
    release = ReleaseProject(
        info=ReleaseInfo(project_urls={"Repository": "https://github.com/acme/demo"}),
        urls=(),
    )

    async def repository_state() -> tuple[DependencyRepositoryState, Evidence | None]:
        return await client.repository("demo", release.info.project_urls, anyio.Semaphore(1))

    state, evidence = anyio.run(repository_state)

    assert state is DependencyRepositoryState.UNKNOWN
    assert evidence is not None
    assert evidence.signal == "dependency:demo:repository-state"
    assert evidence.detail.endswith("ValidationError")


def test_identical_latest_and_resolved_releases_need_only_one_release_request(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\ndependencies = ['Demo==1.0']\n")
    (tmp_path / "uv.lock").write_text(
        "[[package]]\nname = 'demo'\nversion = '1.0'\nsource = { registry = 'pypi' }\n"
    )
    simple = "https://pypi.org/simple/demo/"
    release = "https://pypi.org/pypi/demo/1.0/json"
    transport = StubTransport(
        {
            simple: {"versions": ["1.0"], "project-status": {"status": "mystery"}},
            release: {
                "info": {"project_urls": {}},
                "urls": [{"upload_time_iso_8601": "2025-01-01T00:00:00Z", "yanked": True}],
            },
        }
    )

    fact = anyio.run(DependencyProvider(root=tmp_path, transport=transport).refresh)

    assert sum(url == release for url, _ in transport.calls) == 1
    assert fact.dependencies[0].resolved_release_state is DependencyReleaseState.YANKED
    assert fact.dependencies[0].project_state == "unknown"
    assert {item.signal for item in fact.evidence} == {"dependency:demo:repository-state"}
