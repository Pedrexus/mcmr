import sys
from typing import TYPE_CHECKING

import anyio
import pytest

from mcmr import (
    Boolean,
    Category,
    Numeric,
    RulePolicies,
)
from mcmr.checking.engine import RuleEngine
from mcmr.checking.evaluations import (
    DeferredEvaluation,
    Evaluation,
    TableEvaluationReport,
    TableRuleSummary,
)
from mcmr.checking.session import JudgmentAccumulator, allowed
from mcmr.commands.quality import Judgment, allowance, judgment, listed
from mcmr.domain.contracts import (
    EngineStats,
    Finding,
    RuleLane,
    RuleScope,
)
from mcmr.facts import FunctionFact, ModuleSurfaceFact, SourceSpan
from mcmr.kernel import KernelStats
from mcmr.plugins import fact_table
from mcmr.query.orchestration import TableExecution
from mcmr.rulebook.scope import LanguageScope

from ...support import built_catalog, kernel_binary, needs_kernel, written

if TYPE_CHECKING:
    from pathlib import Path


from .support import TableSessionProbe, definition, module_session


def test_judgment_derives_required_tables_directly_from_rule_annotations(tmp_path: Path) -> None:
    subject = Judgment(binary=tmp_path / "kernel", root=tmp_path, policies=RulePolicies())
    rule = next(
        rule
        for rule in built_catalog().rules
        if rule.primary_family is FunctionFact and not rule.injected
    )

    assert subject.table_families(RuleEngine(rules=[rule]).prepared) == {FunctionFact}


def test_a_report_renders_what_each_effective_policy_accepts() -> None:
    """A failure only reads as a failure beside the allowance it broke."""
    assert allowed(Numeric(maximum=500)) == "<= 500"
    assert allowed(Numeric(minimum=80.0)) == ">= 80"
    assert allowed(Numeric(minimum=1, maximum=3)) == "1..3"
    assert allowed(Boolean()) == "False"
    assert allowed(Category(good={"cohesive"}, neutral={"layered"}, bad={"mixed"})) == (
        "good cohesive | neutral layered | bad mixed"
    )
    assert allowed(None) == ""
    assert allowance(RulePolicies(), definition("ALL-DEMO0001", policy=Numeric(maximum=500))) == (
        "<= 500"
    )


@needs_kernel
def test_a_judgment_is_async_and_stateless(tmp_path: Path) -> None:
    """Sync and async APIs agree without creating cache, evidence, or history state."""
    root = written(
        tmp_path / "checkout",
        {
            "pkg/__init__.py": "",
            "pkg/store.py": "def load():\n    return 1\n",
            "pkg/engine.py": "from .store import load\n\ndef run():\n    return load()\n",
        },
    )
    subject = judgment(
        root,
        select="PY-IMPO0003",
        suffixes="",
        kernel=kernel_binary(),
    )
    before = sorted(path.relative_to(root) for path in root.rglob("*"))

    asynchronous = anyio.run(subject.run_async)
    synchronous = subject.run()

    assert asynchronous.selection == synchronous.selection
    assert asynchronous.rules == synchronous.rules
    assert sorted(path.relative_to(root) for path in root.rglob("*")) == before
    assert not (root / ".mcmr").exists()


def test_a_bounded_judgment_keeps_exact_totals() -> None:
    """A terminal view may drop details only when every aggregate remains exact."""
    counted = definition("ALL-DEMO0001")
    unstated = definition("ALL-DEMO0002", output="str", unit="")
    accumulator = JudgmentAccumulator(RulePolicies(), (counted, unstated), 1)
    findings = [
        Finding(message="first", span=SourceSpan(path="a.py")),
        Finding(message="second", span=SourceSpan(path="a.py")),
    ]
    report = TableEvaluationReport(
        summaries=[
            TableRuleSummary(
                rule=counted.callable,
                observation_count=2,
                unassessed_count=0,
                failure_count=2,
                finding_count=2,
            ),
            TableRuleSummary(
                rule=unstated.callable,
                observation_count=1,
                unassessed_count=1,
                failure_count=0,
                finding_count=0,
            ),
        ],
        failures=(
            Evaluation(
                rule=counted.callable,
                fact="a.py",
                value=1,
                span=SourceSpan(path="a.py"),
                findings=findings,
            ),
        ),
        stats=EngineStats(
            fact_count=3,
            rule_execution_count=2,
            table_query_count=2,
            observation_count=3,
            execution_nanoseconds=7,
        ),
    )
    accumulator.add_table(
        stats=report.stats,
        summaries=report.summaries,
        failures=report.failures,
    )

    judged = accumulator.finish(
        KernelStats(file_count=3),
        runnable={counted.callable, unstated.callable},
        scope=LanguageScope(),
        provider_read_count=2,
    )

    assert (
        judged.failure_count,
        judged.finding_count,
        len(judged.failures),
        judged.unassessed_count,
        judged.engine.rule_execution_count,
        judged.engine.rule_count,
        judged.engine.skipped_rule_count,
        judged.engine.rule_counts_by_lane,
        judged.engine.rule_executions_by_lane,
        judged.engine.skipped_rules,
        judged.engine.table_query_count,
        judged.engine.observation_count,
        judged.engine.execution_nanoseconds,
        accumulator.remaining_failure_limit,
    ) == (
        2,
        2,
        1,
        1,
        2,
        2,
        0,
        {RuleLane.DETERMINISTIC: 2, RuleLane.CONTEXTUAL: 0},
        {RuleLane.DETERMINISTIC: 2, RuleLane.CONTEXTUAL: 0},
        [],
        2,
        3,
        7,
        0,
    )


def test_deferred_evidence_is_built_only_for_a_retained_failure() -> None:
    class EvaluationProbe:
        """Count how often deferred source evidence is requested."""

        def __init__(self, evaluation: Evaluation) -> None:
            self.evaluation = evaluation
            self.calls = 0

        def __call__(self) -> Evaluation:
            self.calls += 1
            return self.evaluation

    counted = definition("ALL-DEMO0001")
    unstated = definition("ALL-DEMO0002", output="str", unit="")
    span = SourceSpan(path="subject.py")
    failing = EvaluationProbe(
        Evaluation(
            rule=counted.callable,
            fact="fail",
            value=1,
            span=span,
            findings=[Finding(message="failed", span=span)],
        )
    )
    dropped = EvaluationProbe(
        Evaluation(
            rule=counted.callable,
            fact="dropped",
            value=2,
            span=span,
            findings=[
                Finding(message="first", span=span),
                Finding(message="second", span=span),
            ],
        )
    )
    accumulator = JudgmentAccumulator(RulePolicies(), (counted, unstated), 1)
    report = TableEvaluationReport(
        summaries=[
            TableRuleSummary(
                rule=counted.callable,
                observation_count=3,
                unassessed_count=0,
                failure_count=2,
                finding_count=3,
            ),
            TableRuleSummary(
                rule=unstated.callable,
                observation_count=1,
                unassessed_count=1,
                failure_count=0,
                finding_count=0,
            ),
        ],
        failures=(
            DeferredEvaluation(
                rule=counted.callable,
                value=1,
                finding_count=1,
                supplier=failing,
            ),
            DeferredEvaluation(
                rule=counted.callable,
                value=2,
                finding_count=2,
                supplier=dropped,
            ),
        ),
        stats=EngineStats(rule_execution_count=2, table_query_count=2, observation_count=4),
    )
    accumulator.add_table(
        stats=report.stats,
        summaries=report.summaries,
        failures=report.failures,
    )

    assert (
        failing.calls,
        dropped.calls,
        accumulator.state.totals[counted.callable].finding_count,
        accumulator.state.failures[counted.callable][0].fact,
    ) == (1, 0, 3, "fail")


def test_a_rule_for_an_absent_language_leaves_the_selected_scope() -> None:
    """A repository holding no TypeScript never selects a TypeScript rule, so none is skipped."""
    general = definition("ALL-DEMO0001")
    python = definition("PY-DEMO0001", scope=RuleScope.PYTHON)
    typescript = definition("TS-DEMO0001", scope=RuleScope.TYPESCRIPT)
    accumulator = JudgmentAccumulator(RulePolicies(), (general, python, typescript), None)

    judged = accumulator.finish(
        KernelStats(),
        runnable={general.callable, python.callable},
        scope=LanguageScope(observed={"python"}),
        provider_read_count=0,
    )

    assert [rule.definition.id for rule in judged.rules] == ["ALL-DEMO0001", "PY-DEMO0001"]
    assert (judged.engine.rule_count, judged.engine.skipped_rules) == (2, [])


def test_a_present_language_keeps_its_rule_and_every_other_skip() -> None:
    """A rule the run could not execute still reads as skipped when its language is present."""
    general = definition("ALL-DEMO0001")
    python = definition("PY-DEMO0001", scope=RuleScope.PYTHON)
    accumulator = JudgmentAccumulator(RulePolicies(), (general, python), None)

    judged = accumulator.finish(
        KernelStats(),
        runnable={general.callable},
        scope=LanguageScope(observed={"python", "rust"}),
        provider_read_count=0,
    )

    assert (judged.engine.rule_count, judged.engine.skipped_rules) == (2, ["PY-DEMO0001"])


def test_a_run_that_observed_no_language_narrows_nothing() -> None:
    """Without one observed language a run proves nothing absent and keeps its whole selection."""
    typescript = definition("TS-DEMO0001", scope=RuleScope.TYPESCRIPT)
    accumulator = JudgmentAccumulator(RulePolicies(), (typescript,), None)

    judged = accumulator.finish(
        KernelStats(),
        runnable=set(),
        scope=LanguageScope(),
        provider_read_count=0,
    )

    assert (judged.engine.rule_count, judged.engine.skipped_rules) == (1, ["TS-DEMO0001"])


@pytest.mark.anyio
async def test_a_language_scoped_selection_reads_the_repository_languages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A selection one absent language could narrow learns which languages the repository holds."""
    engine = RuleEngine(
        rules=[next(item for item in built_catalog().rules if item.id == "TS-MODU0001")]
    )
    monkeypatch.setattr(
        sys.modules[TableExecution.__module__],
        "AnalysisSession",
        lambda *arguments, **keywords: module_session(
            ("ModuleSurfaceFact",),
            fact_table(ModuleSurfaceFact, []),
            languages=("python", "typescript"),
        ),
    )

    coverage = await TableExecution(
        root=tmp_path,
        suffixes=(),
        dependencies=engine.dependencies,
        accumulator=JudgmentAccumulator(RulePolicies(), (), failure_limit=None),
    ).run({ModuleSurfaceFact}, batches=engine.batches, fix_counts=engine.fix_counts)

    assert coverage.languages == {"python", "typescript"}


@pytest.mark.anyio
async def test_a_general_selection_never_pays_for_the_language_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No language can narrow a general selection, so the run never builds the per-module table."""
    monkeypatch.setattr(
        sys.modules[TableExecution.__module__],
        "AnalysisSession",
        lambda *arguments, **keywords: TableSessionProbe(()),
    )

    coverage = await TableExecution(
        root=tmp_path,
        suffixes=(),
        dependencies={},
        accumulator=JudgmentAccumulator(RulePolicies(), (), failure_limit=None),
    ).run(set(), batches=(), fix_counts={})

    assert not coverage.languages


def test_comma_separated_command_values_drop_whitespace_and_empty_items() -> None:
    """A suffix list reaches discovery as exact nonempty items."""
    assert listed("") == []
    assert listed(" .py, .pyi ,") == [".py", ".pyi"]
