import json
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

import anyio
import httpx
import pytest
from mcmr_datahub.provider import DataHubProvider
from mcmr_datahub.transport.recorded import RecordedTransport

from mcmr.commands.interface import RepairMode
from mcmr.commands.quality import check, demo
from mcmr.facts import DataFieldReferenceFact, StringExpressionFact
from mcmr.kernel import Kernel
from mcmr.plugins import ProviderContext, RepositoryTables

from ...support import kernel_binary, needs_kernel, project_root, written

if TYPE_CHECKING:
    from pydantic import JsonValue

_EXAMPLE = project_root() / "examples" / "datahub"
_LITERAL = 'QUERY = "SELECT order_id, legacy_total FROM ecommerce.analytics.orders"\n'


def workspace(root: Path) -> Path:
    """Copy the recorded example into one writable directory the demo can repair."""
    for source in (_EXAMPLE / "pyproject.toml", _EXAMPLE / "pipeline.py"):
        (root / source.name).write_text(source.read_text())
    recordings = root / "recordings"
    recordings.mkdir()
    for source in (_EXAMPLE / "recordings").glob("*.json"):
        (recordings / source.name).write_text(source.read_text())
    return root


@needs_kernel
def test_the_kernel_retains_the_literal_text_and_span_a_rewrite_edits(tmp_path: Path) -> None:
    """The repair anchor is real source rather than a hand-built handle.

    Every DataHub repair replaces one string literal, and the renderer refuses a node whose
    retained text does not match the file. Only the kernel can prove that text arrives, so this
    reads the frontend output instead of a `NodeRef` a test constructed.
    """
    root = written(tmp_path, {"pipeline.py": _LITERAL})
    kernel = Kernel(binary=kernel_binary(), root=root)
    facts = list(
        kernel.build(
            ["StringExpressionFact"], {"StringExpressionFact": StringExpressionFact}
        ).stream(StringExpressionFact)
    )
    nodes = [expression.node for fact in facts for expression in fact.expressions]

    assert [
        (node.kind, node.text, node.span.start_line, node.span.start_column) for node in nodes
    ] == [
        (
            "string",
            '"SELECT order_id, legacy_total FROM ecommerce.analytics.orders"',
            1,
            8,
        )
    ]


def test_a_recording_answers_only_the_operation_and_variables_it_holds(tmp_path: Path) -> None:
    """Replay is a lookup, so an unrecorded operation or argument fails instead of guessing."""
    (tmp_path / "MCMRDataAssets.json").write_text(
        json.dumps([{"variables": {"start": 0}, "response": {"data": {"ok": True}}}])
    )
    transport = RecordedTransport(tmp_path)

    async def ask(operation: str | None, variables: JsonValue) -> httpx.Response:
        request = httpx.Request(
            "POST",
            "http://recorded.invalid/api/graphql",
            json={"query": "{}", "variables": variables, "operationName": operation},
        )
        return await transport.handle_async_request(request)

    assert anyio.run(partial(ask, "MCMRDataAssets", {"start": 0})).json() == {"data": {"ok": True}}
    with pytest.raises(RuntimeError, match="holds no operation MCMRFieldLineage"):
        anyio.run(partial(ask, "MCMRFieldLineage", {"start": 0}))
    with pytest.raises(RuntimeError, match="holds no"):
        anyio.run(partial(ask, "MCMRDataAssets", {"start": 9}))
    with pytest.raises(RuntimeError, match="must name one operation"):
        anyio.run(partial(ask, None, {}))


def test_a_recording_directory_the_configuration_names_has_to_exist(tmp_path: Path) -> None:
    """A path that resolves to nothing fails at the provider boundary, not mid-analysis."""
    context = ProviderContext(
        repository=tmp_path,
        settings={"recorded": "absent"},
        requested={DataFieldReferenceFact},
        dependencies=RepositoryTables(),
    )

    with pytest.raises(ValueError, match="recording directory absent does not exist"):
        anyio.run(DataHubProvider().tables, context)


@needs_kernel
def test_the_recorded_example_reports_owners_repairs_the_proven_rename_and_goes_quiet(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One workflow, no service. Catalog context, a proven repair, and a verified clean rerun."""
    root = workspace(tmp_path)
    check(root, select="data_assets", external=True, report_only=True)
    reviewed = capsys.readouterr().out
    check(root, select="missing_data_field_reference", external=True, repair=RepairMode.APPLY)
    applied = capsys.readouterr().out
    check(root, select="missing_data_field_reference", external=True, report_only=True)
    reran = capsys.readouterr().out

    assert (
        "legacy_total` is absent from the catalog schema" in reviewed,
        "read here has no owner and no description" in reviewed,
        "tagged `PII` has no glossary term" in reviewed,
        "rule verified" in applied,
        (root / "pipeline.py").read_text(),
        "0 failures" in reran,
    ) == (
        True,
        True,
        True,
        True,
        (_EXAMPLE / "pipeline.py").read_text().replace("legacy_total", "total"),
        True,
    )


@needs_kernel
def test_the_demo_command_runs_the_whole_workflow_without_editing_the_example(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The demo copies the example first, so a judge can run it three times unchanged."""
    original = (_EXAMPLE / "pipeline.py").read_text()

    demo(_EXAMPLE)

    output = capsys.readouterr().out
    assert (_EXAMPLE / "pipeline.py").read_text() == original
    assert "The finding is closed" in output
    assert "rule verified" in output
    assert "total " in output
