import importlib.metadata
import tomllib
import urllib.request
from functools import partial
from io import BytesIO
from typing import TYPE_CHECKING

import anyio
import pytest
from pydantic import ValidationError

from mcmr.execution.providers import DependencyProvider, ExternalEvidence
from mcmr.facts import AlertFact, DependencyFact, Fact, SourceSpan
from mcmr.project.dependencies import DependencyInventory, DependencyRefresher, UrlJsonTransport

if TYPE_CHECKING:
    from pathlib import Path


def test_external_evidence_resolves_only_registered_fact_families_in_memory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fact = DependencyFact(key="dependencies", span=SourceSpan(path="pyproject.toml"))

    async def collect(provider: DependencyProvider) -> list[DependencyFact]:
        assert provider.repository == tmp_path
        return [fact]

    monkeypatch.setattr(DependencyProvider, "collect", collect)
    evidence = ExternalEvidence.for_repository(tmp_path)

    families: set[type[Fact]] = {DependencyFact, AlertFact}
    tables = anyio.run(evidence.tables, families)

    assert list(tables) == [DependencyFact]
    table = tables[DependencyFact]
    assert table.frame(next(iter(table.relation_type))).get_column("fact_id").to_list() == [
        "dependencies"
    ]


def test_dependency_provider_collects_without_writing_repository_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fact = DependencyFact(key="dependencies", span=SourceSpan(path="pyproject.toml"))

    async def refresh(refresher: DependencyRefresher) -> DependencyFact:
        assert refresher.root == tmp_path
        return fact

    monkeypatch.setattr(DependencyRefresher, "refresh", refresh)

    assert anyio.run(DependencyProvider(repository=tmp_path).collect) == [fact]
    assert list(tmp_path.iterdir()) == []


@pytest.fixture
def inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> DependencyInventory:
    """Build an inventory with declarations from every supported local source."""
    (tmp_path / "pyproject.toml").write_text(
        """[project]
dependencies = ['Demo>=1,<3', 'Runtime>=2']
[project.optional-dependencies]
dev = ['Dev>=2']
[build-system]
requires = ['Build>=1']
"""
    )
    (tmp_path / "chefe.toml").write_text(
        """[python.deps]
demo = '>=1,<3'
extra = '*'
local = { path = '../local', editable = true }
[dev.python.deps]
tool = '>=4'
"""
    )
    (tmp_path / "uv.lock").write_text(
        """[[package]]
name = 'demo'
version = '1.0'
source = { registry = 'pypi' }
[[package]]
name = 'demo'
version = '2.5'
source = { registry = 'pypi' }
[[package]]
name = 'demo'
version = '3.1'
source = { registry = 'pypi' }
[[package]]
name = 'demo'
version = '2.0'
source = { path = '../demo' }
[[package]]
name = 'demo'
version = 2
source = { registry = 'pypi' }
"""
    )
    installed = {"runtime": "2.2", "extra": "1.0", "local": "bad-version"}

    def version(name: str) -> str:
        try:
            return installed[name]
        except KeyError as error:
            raise importlib.metadata.PackageNotFoundError(name) from error

    monkeypatch.setattr(importlib.metadata, "version", version)
    return DependencyInventory(root=tmp_path)


def test_inventory_merges_standard_and_chefe_declarations(
    inventory: DependencyInventory,
) -> None:
    by_name = {item.name: item for item in inventory.declarations()}

    assert list(by_name) == ["build", "demo", "dev", "extra", "local", "runtime", "tool"]
    assert (by_name["demo"].is_development, by_name["dev"].is_development) == (False, True)


def test_inventory_resolves_uv_before_installed_distributions(
    inventory: DependencyInventory,
) -> None:
    demo = {item.name: item for item in inventory.declarations()}["demo"]
    resolution = inventory.resolved_version(name=demo.name, requirement=demo.requirement)

    assert resolution.version == "2.5"


def test_inventory_retains_invalid_and_missing_installed_versions(
    inventory: DependencyInventory,
) -> None:
    by_name = {item.name: item for item in inventory.declarations()}
    local = inventory.resolved_version(name="local", requirement=by_name["local"].requirement)
    tool = inventory.resolved_version(name="tool", requirement=by_name["tool"].requirement)

    assert "valid PEP 440" in (local.failure or "")
    assert tool.failure == "dependency is not installed"


def test_inventory_rejects_an_installed_version_outside_the_requirement(
    inventory: DependencyInventory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(importlib.metadata, "version", lambda _name: "1.0")
    runtime = {item.name: item for item in inventory.declarations()}["runtime"]
    resolution = inventory.resolved_version(name=runtime.name, requirement=runtime.requirement)

    assert resolution.failure == "installed version does not satisfy declaration"


def test_inventory_accepts_a_matching_installed_version(
    inventory: DependencyInventory,
) -> None:
    """The environment fallback retains a valid installed version when no lock row exists."""
    runtime = {item.name: item for item in inventory.declarations()}["runtime"]

    resolution = inventory.resolved_version(name=runtime.name, requirement=runtime.requirement)

    assert resolution.version == "2.2"


def test_inventory_without_manifests_has_no_declarations(tmp_path: Path) -> None:
    assert DependencyInventory(root=tmp_path / "absent").declarations() == []


def test_inventory_refuses_malformed_manifests_and_unsupported_requirement_shapes(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project\n")
    with pytest.raises(tomllib.TOMLDecodeError):
        DependencyInventory(root=tmp_path).declarations()

    with pytest.raises(ValidationError):
        DependencyInventory.requirement_adapter.validate_python([1])
    with pytest.raises(ValidationError):
        DependencyInventory.stated("demo", ["not", "a", "table"])


def test_standard_transport_sets_bounded_headers_and_decodes_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[tuple[urllib.request.Request, int]] = []

    def open_request(request: urllib.request.Request, timeout: int) -> BytesIO:
        observed.append((request, timeout))
        return BytesIO(b'{"archived": true}')

    monkeypatch.setattr(urllib.request, "urlopen", open_request)
    transport = UrlJsonTransport(timeout_seconds=12, github_token="secret")

    document = anyio.run(
        partial(
            transport.get,
            "https://api.github.com/repos/a/b",
            accept="application/json",
        )
    )

    assert document == {"archived": True}
    request, timeout = observed[0]
    assert (
        timeout,
        request.get_header("Authorization"),
        request.get_header("User-agent"),
    ) == (12, "Bearer secret", "mcmr-dependency-evidence")
    transport.read("https://pypi.org/simple/demo/", accept="application/json")
    assert observed[1][0].get_header("Authorization") is None
