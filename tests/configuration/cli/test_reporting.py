import importlib
import json
import runpy
import sys
from pathlib import Path

import pytest

from mcmr import (
    ExecutionOverride,
)
from mcmr.commands import interface
from mcmr.commands.insight import catalog, replacement
from mcmr.commands.interface import RepairMode, RuleCoverage
from mcmr.commands.quality import (
    backends,
    check,
    judgment,
)
from mcmr.kernel import locate
from mcmr.presentation.reports import CheckFormat

_PACKAGE = Path(__file__).parents[3]


def test_cli_module_invokes_the_registered_application(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[bool] = []
    importlib.import_module("mcmr.commands.cli")
    monkeypatch.delitem(sys.modules, "mcmr.commands.cli")
    monkeypatch.setattr(interface, "app", lambda: called.append(True))

    runpy.run_module("mcmr.commands.cli", run_name="__main__")

    assert called == [True]


def test_check_can_write_complete_json_and_report_failures_without_exiting(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CI receives the complete typed report while report-only audits retain a zero status."""
    if not locate(_PACKAGE).exists():
        pytest.skip("the analysis kernel is not built")
    (tmp_path / "sample.py").write_text("import os\nimport sys\n")
    output = tmp_path / "report.json"

    check(
        tmp_path,
        select="PY-IMPO0003",
        format=CheckFormat.JSON,
        limit=1,
        output=output,
        report_only=True,
    )

    rendered = output.read_text()
    document = json.loads(rendered)
    assert (
        document["total_failure_count"],
        len(document["failures"]),
        '"rule": "PY-IMPO0003"' in rendered,
        rendered == capsys.readouterr().out,
    ) == (2, 2, True, True)


def test_backends_shows_the_normal_check_backend_without_running_it(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """[tool.mcmr.execution]
contextual = true
[tool.mcmr.contextual]
model = 'gpt-test'
reasoning_effort = 'medium'
"""
    )

    backends(tmp_path)

    output = capsys.readouterr().out
    assert "MCMR contextual backend" in output
    assert "enabled" in output
    assert "gpt-test" in output
    assert "medium" in output


def test_a_check_can_enable_contextual_rules_for_one_run(tmp_path: Path) -> None:
    configured = judgment(
        tmp_path,
        select="",
        suffixes="",
        kernel=None,
        contextual=ExecutionOverride.ENABLED,
    )

    assert configured.configuration.execution.contextual is True


def test_requiring_every_selected_rule_rejects_missing_external_evidence(
    tmp_path: Path,
) -> None:
    if not locate(_PACKAGE).exists():
        pytest.skip("the analysis kernel is not built")
    (tmp_path / "sample.py").write_text('"""A module."""\n')

    with pytest.raises(SystemExit):
        check(
            tmp_path,
            select="ALL-ARCH1005",
            format=CheckFormat.CONCISE,
            contextual=True,
            external=True,
            rule_coverage=RuleCoverage.ALL,
        )


def test_requiring_every_selected_rule_rejects_a_configured_disabled_rule(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if not locate(_PACKAGE).exists():
        pytest.skip("the analysis kernel is not built")
    (tmp_path / "sample.py").write_text('"""A module."""\n')
    (tmp_path / "pyproject.toml").write_text("[tool.mcmr.rules.ALL-MODU0001]\nenabled = false\n")

    with pytest.raises(SystemExit):
        check(
            tmp_path,
            select="ALL-MODU0001",
            format=CheckFormat.CONCISE,
            rule_coverage=RuleCoverage.ALL,
        )

    output = capsys.readouterr().out
    assert "0/1 rules" in output
    assert "1 skipped" in output


def test_catalog_exports_the_live_typed_registry(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "catalog.json"

    catalog(output)

    rendered = output.read_text()
    assert '"schema": 1' in rendered
    assert rendered.count('"id": ') == 275
    assert "exported 275 live rules" in capsys.readouterr().out

    catalog()
    assert '"ALL-ABST1001"' in capsys.readouterr().out


def test_replacement_report_names_every_remaining_product_gap(
    capsys: pytest.CaptureFixture[str],
) -> None:
    replacement()

    output = capsys.readouterr().out
    assert "GE4M replacement" in output
    assert "205/205 rules" in output
    assert "18/18 capabilities" in output
    assert "0 missing" in output


def test_check_previews_a_safe_fix_without_changing_source(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A preview is a rendered diff and never an implicit write."""
    if not locate(_PACKAGE).exists():
        pytest.skip("the analysis kernel is not built")
    module = tmp_path / "sample.py"
    source = 'from __future__ import annotations\n\n"""A module."""\n'
    module.write_text(source)

    with pytest.raises(SystemExit):
        check(tmp_path, select="PY-TYPE0001", repair=RepairMode.PREVIEW)

    output = capsys.readouterr().out
    assert (
        "preview" in output,
        "PY-TYPE0001" in output,
        "-from __future__ import annotations" in output,
        module.read_text(),
    ) == (True, True, True, source)
