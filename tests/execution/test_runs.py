import sys
from importlib.metadata import EntryPoint
from types import SimpleNamespace
from typing import TYPE_CHECKING

import anyio
import pytest

from mcmr import (
    Boolean,
    Category,
    ContextBackend,
    ContextualConfiguration,
    ExecutionConfiguration,
    MCMRConfiguration,
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
from mcmr.checking.session import Judgment, JudgmentAccumulator, TableExecution, allowed
from mcmr.commands.quality import allowance, judgment, listed
from mcmr.domain.contracts import (
    EngineStats,
    Finding,
    RuleDefinition,
    RuleDocumentation,
    RuleIdentity,
    RuleLane,
    RuleScope,
)
from mcmr.execution import ClassificationBackend, CodexBackend
from mcmr.execution.providers import DependencyProvider, ExternalEvidence
from mcmr.facts import DependencyFact, Fact, FunctionFact, SourceSpan
from mcmr.kernel import KernelStats, requested_fact
from mcmr.table import RepositoryTables, fact_table

from ..support import built_catalog, kernel_binary, needs_kernel, written
from .providers.fact import PluginFact
from .providers.provider import (
    PluginProvider,
    empty_plugin_provider,
    invalid_plugin_provider,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence
    from pathlib import Path


class TableSessionProbe:
    """Return a controlled native marker stream for integration guards."""

    def __init__(self, markers: Sequence[str]) -> None:
        self.markers = markers

    @staticmethod
    def kernel_stats(total_nanoseconds: int) -> KernelStats:
        """Return the bounded timing the coordinator supplies after table execution."""
        return KernelStats(total_nanoseconds=total_nanoseconds)

    def table_markers(self) -> Iterator[str]:
        """Yield the marker sequence under test."""
        yield from self.markers


def definition(
    identifier: str,
    *,
    output: str = "int",
    unit: str = "count",
    policy: Numeric | None = None,
) -> RuleDefinition:
    """Build one compact deterministic definition for accumulator tests."""
    return RuleDefinition(
        identity=RuleIdentity(
            id=identifier,
            callable=f"mcmr.rules.general.deterministic.demo.r0001.{identifier.lower()}",
            scope=RuleScope.GENERAL,
            lane=RuleLane.DETERMINISTIC,
            family="demo",
            fact="ModuleFact",
        ),
        output=output,
        unit=unit,
        policy=policy,
        documentation=RuleDocumentation(summary="", definition="", examples=""),
    )


def test_judgment_injects_only_the_explicitly_enabled_contextual_backend(
    tmp_path: Path,
) -> None:
    """Normal checks stay offline until contextual execution is explicitly enabled."""
    base = Judgment(binary=tmp_path / "kernel", root=tmp_path, policies=RulePolicies())

    assert base.dependencies() == {}

    configured = base.model_copy(
        update={
            "configuration": MCMRConfiguration(
                execution=ExecutionConfiguration(contextual=True),
                contextual=ContextualConfiguration(
                    backend=ContextBackend.CODEX,
                    binary="codex-test",
                    model="gpt-test",
                    reasoning_effort="medium",
                    timeout_seconds=30,
                ),
            )
        }
    )
    backend = configured.dependencies()[ClassificationBackend]

    assert isinstance(backend, CodexBackend)
    assert backend.binary == "codex-test"
    assert backend.model == "gpt-test"
    assert backend.reasoning_effort == "medium"
    assert backend.timeout_seconds == 30


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("markers", "message"),
    [
        ((), "omitted fact families FunctionFact"),
        (("ModuleFact",), "unexpected table ModuleFact"),
        (("FunctionFact", "FunctionFact"), "repeated table FunctionFact"),
    ],
)
async def test_table_judgment_rejects_an_invalid_native_marker_stream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    markers: tuple[str, ...],
    message: str,
) -> None:
    session = TableSessionProbe(markers)
    monkeypatch.setattr(
        sys.modules[TableExecution.__module__],
        "AnalysisSession",
        lambda *arguments, **keywords: session,
    )
    subject = Judgment(binary=tmp_path / "kernel", root=tmp_path, policies=RulePolicies())
    accumulator = JudgmentAccumulator(RulePolicies(), (), failure_limit=None)
    rule = next(
        rule
        for rule in built_catalog().rules
        if requested_fact(rule) is FunctionFact and not rule.injected
    )

    with pytest.raises(RuntimeError, match=message):
        engine = RuleEngine(rules=[rule])
        await TableExecution(
            root=subject.root,
            suffixes=subject.suffixes,
            dependencies=engine.dependencies,
            accumulator=accumulator,
        ).run(
            {FunctionFact},
            batches=engine.batches,
            fix_counts=engine.fix_counts,
        )


@pytest.mark.anyio
async def test_table_judgment_executes_an_in_memory_external_family(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A selected provider table joins the same request-local execution graph as native facts."""
    catalog = built_catalog()
    definition = next(item for item in catalog.definitions if item.id == "ALL-DEPE0002")
    rule = next(item for item in catalog.rules if item.callable_path == definition.callable)
    dependency = DependencyFact(key="dependencies", span=SourceSpan(path="pyproject.toml"))

    async def tables(
        evidence: ExternalEvidence,
        families: set[type[Fact]],
    ) -> RepositoryTables:
        assert evidence.repository == tmp_path and families == {DependencyFact}
        provided = RepositoryTables()
        provided.add(fact_table(DependencyFact, [dependency]))
        return provided

    monkeypatch.setattr(
        sys.modules[TableExecution.__module__],
        "AnalysisSession",
        lambda *arguments, **keywords: TableSessionProbe(()),
    )
    monkeypatch.setattr(ExternalEvidence, "tables", tables)

    engine = RuleEngine(rules=[rule])
    _, runnable, provider_read_count = await TableExecution(
        root=tmp_path,
        suffixes=(),
        dependencies=engine.dependencies,
        accumulator=JudgmentAccumulator(RulePolicies(), (definition,), failure_limit=None),
    ).run(
        {DependencyFact},
        batches=engine.batches,
        fix_counts=engine.fix_counts,
    )

    assert (runnable, provider_read_count) == ({definition.callable}, 1)


@pytest.mark.anyio
async def test_external_fact_plugins_own_custom_families(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An installed provider receives only its requested families and named settings."""
    entry = EntryPoint(
        name="datahub",
        value=f"{PluginProvider.__module__}:{PluginProvider.__name__}",
        group="mcmr.providers",
    )
    monkeypatch.setattr(
        "mcmr.execution.providers.evidence.metadata.entry_points",
        lambda **selection: (entry,) if selection == {"group": "mcmr.providers"} else (),
    )

    tables = await ExternalEvidence.for_repository(
        tmp_path,
        {"datahub": {"catalog": "http://localhost:8080"}},
    ).tables({PluginFact})

    assert list(tables) == [PluginFact]
    assert tables[PluginFact].facts().collect().item(0, "value") == "http://localhost:8080"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("factory", "message"),
    [
        ("not a provider", "must load a callable factory"),
        (invalid_plugin_provider, "does not implement FactProvider"),
    ],
)
async def test_external_fact_plugins_reject_invalid_entry_points(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: str | Callable[..., SimpleNamespace],
    message: str,
) -> None:
    """Provider discovery fails before an invalid plugin can supply evidence."""
    entry = SimpleNamespace(
        name="invalid",
        value=str(factory),
        load=lambda: factory,
    )
    monkeypatch.setattr(
        "mcmr.execution.providers.evidence.metadata.entry_points",
        lambda **selection: (entry,),
    )

    with pytest.raises(TypeError, match=message):
        await ExternalEvidence.for_repository(tmp_path).tables({PluginFact})


@pytest.mark.anyio
async def test_external_fact_plugins_have_exact_unique_family_ownership(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A family has one owner and that owner returns exactly the requested table."""
    entries = (
        EntryPoint(
            name="first",
            value=f"{PluginProvider.__module__}:{PluginProvider.__name__}",
            group="mcmr.providers",
        ),
        EntryPoint(
            name="second",
            value=f"{PluginProvider.__module__}:{PluginProvider.__name__}",
            group="mcmr.providers",
        ),
    )
    monkeypatch.setattr(
        "mcmr.execution.providers.evidence.metadata.entry_points",
        lambda **selection: entries,
    )
    with pytest.raises(ValueError, match="owned by providers first and second"):
        await ExternalEvidence.for_repository(tmp_path).tables({PluginFact})

    empty = EntryPoint(
        name="empty",
        value=f"{empty_plugin_provider.__module__}:{empty_plugin_provider.__name__}",
        group="mcmr.providers",
    )
    monkeypatch.setattr(
        "mcmr.execution.providers.evidence.metadata.entry_points",
        lambda **selection: (empty,),
    )
    with pytest.raises(RuntimeError, match="did not supply exactly PluginFact"):
        await ExternalEvidence.for_repository(tmp_path).tables({PluginFact})

    assert not list(await DependencyProvider(repository=tmp_path).tables(set()))


def test_judgment_derives_required_tables_directly_from_rule_annotations(tmp_path: Path) -> None:
    subject = Judgment(binary=tmp_path / "kernel", root=tmp_path, policies=RulePolicies())
    rule = next(
        rule
        for rule in built_catalog().rules
        if requested_fact(rule) is FunctionFact and not rule.injected
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
        provider_read_count=2,
        fix_count=4,
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


def test_comma_separated_command_values_drop_whitespace_and_empty_items() -> None:
    """A suffix list reaches discovery as exact nonempty items."""
    assert listed("") == []
    assert listed(" .py, .pyi ,") == [".py", ".pyi"]
