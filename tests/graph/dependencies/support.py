from typing import TYPE_CHECKING, cast

import anyio

from mcmr.execution.providers import DependencyProvider

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from pydantic import JsonValue

    from mcmr.facts import DependencyFact


class StubTransport:
    """Return controlled JSON documents and bounded transport failures by exact URL."""

    def __init__(self, responses: Mapping[str, JsonValue | OSError]) -> None:
        self.responses = dict(responses)
        self.calls: list[tuple[str, str]] = []

    async def get(self, url: str, *, accept: str = "application/json") -> JsonValue:
        self.calls.append((url, accept))
        response = self.responses[url]
        if isinstance(response, OSError):
            raise response
        return response


def complete_refresh(root: Path) -> tuple[DependencyFact, StubTransport]:
    """Build one fully observed dependency refresh and its transport trace."""
    (root / "pyproject.toml").write_text("[project]\ndependencies = ['Demo>=1,<3']\n")
    (root / "uv.lock").write_text(
        "[[package]]\nname = 'demo'\nversion = '1.0'\nsource = { registry = 'pypi' }\n"
    )
    simple, resolved, latest, repository = (
        "https://pypi.org/simple/demo/",
        "https://pypi.org/pypi/demo/1.0/json",
        "https://pypi.org/pypi/demo/2.0/json",
        "https://api.github.com/repos/acme/demo",
    )
    release_info = {"project_urls": {"Source": "https://github.com/acme/demo.git"}}
    responses = cast(
        "dict[str, JsonValue | OSError]",
        {
            simple: {
                "versions": ["1.0", "2.0", "3.0"],
                "project-status": {"status": "active"},
                "ignored": True,
            },
            resolved: {
                "info": release_info,
                "urls": [{"upload_time_iso_8601": "2024-01-02T00:00:00Z", "yanked": False}],
            },
            latest: {
                "info": release_info,
                "urls": [{"upload_time_iso_8601": "2025-01-03T00:00:00Z", "yanked": False}],
            },
            repository: {"archived": True},
        },
    )
    transport = StubTransport(responses)
    fact = anyio.run(DependencyProvider(root=root, transport=transport, workers=2).refresh)
    return fact, transport
