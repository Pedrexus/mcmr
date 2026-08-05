from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from mcmr import (
    ContextBackend,
    ContextualConfiguration,
)
from mcmr.commands.interface import FixPresentation
from mcmr.commands.projection import floor
from mcmr.commands.quality import (
    check,
    contextual_experiment,
    model_sweep,
)
from mcmr.contextual.corpus import ContextualCase, ContextualCorpus, ContextualExpectation
from mcmr.contextual.evaluation import (
    BackendProfile,
    ContextualExperiment,
    ContextualExperimentReport,
    ContextualSweep,
    ContextualSweepReport,
    ContextualSweepResult,
    ContextualTrial,
    ProfileExperiment,
)
from mcmr.domain.contracts import FixSafety, ModelProvenance, RuleSetting
from mcmr.execution import ClassificationBackend, CodexBackend
from mcmr.facts import Evidence
from mcmr.presentation import FixRefusal, RenderedFix
from mcmr.presentation.fixes import RenderedFile
from mcmr.presentation.reports import CheckFormat
from mcmr.project import locate

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mcmr.rulebook.catalog import Catalog

_PACKAGE = Path(__file__).parents[3]


def test_floor_cli_prints_the_report_without_persistence() -> None:
    floor(samples=1, facts=60)


def test_floor_cli_can_persist_the_report(tmp_path: Path) -> None:
    output = tmp_path / "floor.json"
    floor(samples=1, facts=60, output=output)
    assert '"rule_count":' in output.read_text()


def test_contextual_experiment_cli_renders_and_writes_the_labeled_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def experimented(
        self: ContextualExperiment,
        catalog: Catalog,
        corpus: ContextualCorpus,
        configuration: ContextualConfiguration,
        settings: dict[str, dict[str, RuleSetting]],
    ) -> ContextualExperimentReport:
        assert self.workers == 2
        assert catalog.definitions and corpus.cases and configuration and not settings
        profile = BackendProfile(
            name="terra-low",
            backend=ContextBackend.CODEX,
            model="gpt-5.6-terra",
            reasoning_effort="low",
        )
        return ContextualExperimentReport(
            profiles=[
                ProfileExperiment(
                    profile=profile,
                    elapsed_seconds=1.25,
                    trials=[
                        ContextualTrial(
                            profile=profile.name,
                            rule="ALL-ARCH1001",
                            case="cohesive",
                            expected="cohesive",
                            actual="cohesive",
                            passed=True,
                        ),
                        ContextualTrial(
                            profile=profile.name,
                            rule="ALL-ARCH1002",
                            case="mixed",
                            expected="cohesive",
                            actual="mixed",
                            passed=False,
                        ),
                    ],
                )
            ]
        )

    labels = tmp_path / "labels.json"
    labels.write_text(
        ContextualCorpus(
            cases=[
                ContextualCase(
                    name="cohesive",
                    rule="ALL-ARCH1001",
                    fact_id="case:cohesive",
                    path="src/example.py",
                    subject={"shape": "cohesive"},
                    evidence=[Evidence(signal="reviewed", detail="cohesive", source="review")],
                    expected=ContextualExpectation(classification="cohesive"),
                )
            ]
        ).model_dump_json(),
        encoding="utf-8",
    )
    output_path = tmp_path / "experiment.json"
    monkeypatch.setattr(ContextualExperiment, "run", experimented)

    contextual_experiment(labels, root=tmp_path, workers=2, output=output_path)
    contextual_experiment(labels, root=tmp_path, workers=2)

    output = capsys.readouterr().out
    assert all(
        expected in output
        for expected in (
            "MCMR contextual experiment",
            "terra-low",
            "ALL-ARCH1001",
            "ALL-ARCH1002",
            "unresolved",
        )
    )
    assert '"ALL-ARCH1001": "terra-low"' in output_path.read_text()


def test_model_sweep_cli_runs_every_contextual_rule_and_writes_the_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def swept(
        self: ContextualSweep,
        catalog: Catalog,
        settings: dict[str, dict[str, RuleSetting]],
    ) -> ContextualSweepReport:
        assert self.workers == 2
        assert isinstance(self.backend, CodexBackend)
        assert self.backend.model == "gpt-test"
        assert catalog.definitions and not settings
        return ContextualSweepReport(
            results=[
                ContextualSweepResult(
                    rule="ALL-ARCH1001",
                    value="cohesive",
                    finding_count=1,
                    provenance=ModelProvenance(
                        backend="codex",
                        model="gpt-test",
                        reasoning_effort="low",
                        input_tokens=120,
                        output_tokens=12,
                    ),
                )
            ],
            elapsed_seconds=1.25,
        )

    (tmp_path / "pyproject.toml").write_text(
        "[tool.mcmr.contextual]\nmodel = 'gpt-test'\nreasoning_effort = 'low'\n"
    )
    output_path = tmp_path / "sweep.json"
    monkeypatch.setattr(ContextualSweep, "run", swept)

    model_sweep(
        tmp_path,
        workers=2,
        model="gpt-test",
        reasoning_effort="low",
        output=output_path,
    )
    model_sweep(tmp_path, workers=2)

    rendered = capsys.readouterr().out
    assert all(
        expected in rendered
        for expected in (
            "MCMR contextual sweep",
            "ALL-ARCH1001",
            "1 rules in 1.2s",
            "120 input tokens",
            "0 cached",
            "12 output tokens",
            "0 explanation characters",
            "0 errors",
        )
    )
    assert '"rule": "ALL-ARCH1001"' in output_path.read_text()


def test_model_sweep_cli_overrides_the_configured_backend(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit backend override reaches another provider without editing the project."""
    swept: list[ClassificationBackend] = []

    async def record(
        self: ContextualSweep,
        catalog: Catalog,
        settings: Mapping[str, dict[str, RuleSetting]],
    ) -> ContextualSweepReport:
        del catalog, settings
        swept.append(self.backend)
        return ContextualSweepReport(
            results=[
                ContextualSweepResult(
                    rule="ALL-ARCH1001",
                    value="cohesive",
                    finding_count=0,
                    provenance=ModelProvenance(
                        backend=self.backend.name,
                        model=self.backend.model,
                        reasoning_effort=self.backend.reasoning_effort,
                    ),
                )
            ],
            elapsed_seconds=0.5,
        )

    (tmp_path / "pyproject.toml").write_text("[tool.mcmr.contextual]\nmodel = 'gpt-test'\n")
    monkeypatch.setattr(ContextualSweep, "run", record)

    model_sweep(tmp_path, backend="claude", model="claude-sonnet-5", reasoning_effort="high")
    model_sweep(tmp_path, backend="openrouter", model="deepseek/deepseek-v4-flash-0731")

    assert [backend.name for backend in swept] == ["claude", "openrouter"]
    assert [backend.model for backend in swept] == [
        "claude-sonnet-5",
        "deepseek/deepseek-v4-flash-0731",
    ]
    assert (swept[0].reasoning_effort, swept[1].reasoning_effort) == ("high", "medium")
    assert "MCMR contextual sweep" in capsys.readouterr().out


def test_check_fails_a_repository_that_breaks_a_rule_policy(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`mcmr check` judges what it found and exits nonzero only on a failure."""
    if not locate(_PACKAGE).exists():
        pytest.skip("the analysis kernel is not built")
    (tmp_path / "sample.py").write_text("import os\n\n\ndef load(name):\n    return name\n")

    with pytest.raises(SystemExit):
        check(tmp_path)

    output = capsys.readouterr().out
    assert "PY-IMPO0003" in output
    assert "1 files" in output


def test_check_passes_a_repository_that_meets_a_rule_policy(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Nothing to report means no failure and no exit code."""
    if not locate(_PACKAGE).exists():
        pytest.skip("the analysis kernel is not built")
    (tmp_path / "sample.py").write_text('"""A module."""\n')

    check(tmp_path, select="PY-IMPO0003")

    assert "0 failures" in capsys.readouterr().out


def test_plain_check_presentation_stays_explicit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Stable text output remains available for an empty result."""
    if not locate(_PACKAGE).exists():
        pytest.skip("the analysis kernel is not built")
    (tmp_path / "sample.py").write_text('"""A module."""\n')
    check(
        tmp_path,
        select="PY-IMPO0003",
        format=CheckFormat.CONCISE,
    )
    assert "0 failures" in capsys.readouterr().out


def test_empty_and_refused_fix_presentations_stay_explicit() -> None:
    """Fix presentation distinguishes silence from an explicit refusal."""
    stream = StringIO()
    presentation = FixPresentation(Console(file=stream, color_system=None))
    presentation.show(applied=(), previewed=(), refused=())
    assert not stream.getvalue()
    presentation.show(
        applied=(),
        previewed=(),
        refused=(FixRefusal(rule="PY-DEMO0001", summary="Repair.", reason="stale source"),),
    )
    assert "refused" in stream.getvalue()
    assert "stale source" in stream.getvalue()


def test_fix_previews_render_each_safety_and_changed_line() -> None:
    """A mixed preview presents its count and changed source."""
    stream = StringIO()
    presentation = FixPresentation(Console(file=stream, color_system=None))
    previews = [
        RenderedFix(
            rule="PY-DEMO0001",
            callable="demo.repair",
            message="Repair it.",
            summary="Repair.",
            safety=safety,
            files=[
                RenderedFile(
                    path="sample.py",
                    original=b"old\n",
                    revised=b"new\n",
                )
            ],
        )
        for safety in (FixSafety.SAFE, FixSafety.REVIEW)
    ]
    presentation.show(applied=(), previewed=previews, refused=())
    assert "preview" in stream.getvalue()
    assert "Count" in stream.getvalue()
    assert "-old" in stream.getvalue()
