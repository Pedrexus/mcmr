import sys
from importlib.metadata import EntryPoint
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from pydantic import TypeAdapter

from mcmr import (
    ContextBackend,
    ContextualConfiguration,
    ExecutionConfiguration,
    MCMRConfiguration,
    RulePolicies,
)
from mcmr.checking.engine import RuleEngine
from mcmr.checking.session import JudgmentAccumulator
from mcmr.commands.quality import Judgment
from mcmr.execution import ClassificationBackend, CodexBackend
from mcmr.execution.providers import (
    DependencyProvider,
    ExternalEvidence,
    ProviderExecutionError,
)
from mcmr.facts import AlertFact, DependencyFact, FunctionFact, SourceSpan
from mcmr.plugins import Fact, NonEmptyStr, RepositoryTables, fact_table
from mcmr.query.orchestration import TableExecution

from ...support import built_catalog
from ..providers.cases import DependentPluginProvider, EmptyPluginProvider
from ..providers.fact import PluginFact
from ..providers.provider import PluginProvider, invalid_plugin_provider

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

from mcmr.plugins import ProviderContext

from .support import TableSessionProbe, dependency_rules, module_session


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
        if rule.primary_family is FunctionFact and not rule.injected
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
        dependencies: RepositoryTables,
    ) -> RepositoryTables:
        assert evidence.repository == tmp_path and families == {DependencyFact}
        assert not dependencies
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
    coverage = await TableExecution(
        root=tmp_path,
        suffixes=(),
        dependencies=engine.dependencies,
        accumulator=JudgmentAccumulator(RulePolicies(), (definition,), failure_limit=None),
    ).run(
        {DependencyFact},
        batches=engine.batches,
        fix_counts=engine.fix_counts,
    )

    assert (coverage.runnable, coverage.provider_read_count) == ({definition.callable}, 1)


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
async def test_external_fact_validation_failures_name_the_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid provider configuration reaches callers as one named boundary failure."""

    async def rejected(provider: PluginProvider, context: ProviderContext) -> RepositoryTables:
        TypeAdapter(NonEmptyStr).validate_python("")
        return RepositoryTables()

    entry = EntryPoint(
        name="datahub",
        value=f"{PluginProvider.__module__}:{PluginProvider.__name__}",
        group="mcmr.providers",
    )
    monkeypatch.setattr(
        "mcmr.execution.providers.evidence.metadata.entry_points",
        lambda **selection: (entry,),
    )
    monkeypatch.setattr(PluginProvider, "tables", rejected)

    with pytest.raises(ProviderExecutionError, match="external provider `datahub` failed"):
        await ExternalEvidence.for_repository(tmp_path).tables({PluginFact})


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
        value=f"{EmptyPluginProvider.__module__}:{EmptyPluginProvider.__name__}",
        group="mcmr.providers",
    )
    monkeypatch.setattr(
        "mcmr.execution.providers.evidence.metadata.entry_points",
        lambda **selection: (empty,),
    )
    with pytest.raises(RuntimeError, match="did not supply exactly PluginFact"):
        await ExternalEvidence.for_repository(tmp_path).tables({PluginFact})

    assert not list(await ExternalEvidence.for_repository(tmp_path).tables(set()))


@pytest.mark.anyio
async def test_external_fact_plugins_receive_declared_native_tables(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider sees its declared native table and no undeclared table."""
    entry = EntryPoint(
        name="dependent",
        value=f"{DependentPluginProvider.__module__}:{DependentPluginProvider.__name__}",
        group="mcmr.providers",
    )
    monkeypatch.setattr(
        "mcmr.execution.providers.evidence.metadata.entry_points",
        lambda **selection: (entry,),
    )
    dependencies = RepositoryTables()
    dependencies.add(fact_table(FunctionFact, []))

    tables = await ExternalEvidence.for_repository(tmp_path).tables(
        {PluginFact},
        dependencies,
    )

    assert tables[PluginFact].facts().collect().item(0, "value") == "0"


@pytest.mark.anyio
async def test_external_fact_plugins_reject_missing_dependencies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider execution stops when a declared native input is unavailable."""
    entry = EntryPoint(
        name="dependent",
        value=f"{DependentPluginProvider.__module__}:{DependentPluginProvider.__name__}",
        group="mcmr.providers",
    )
    monkeypatch.setattr(
        "mcmr.execution.providers.evidence.metadata.entry_points",
        lambda **selection: (entry,),
    )

    with pytest.raises(RuntimeError, match="unavailable families FunctionFact"):
        await ExternalEvidence.for_repository(tmp_path).tables({PluginFact})


@pytest.mark.anyio
async def test_external_fact_plugins_reject_dependency_cycles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider cycle fails before either provider performs external work."""
    entries = (
        EntryPoint(
            name="dependencies",
            value=f"{DependencyProvider.__module__}:{DependencyProvider.__name__}",
            group="mcmr.providers",
        ),
        EntryPoint(
            name="dependent",
            value=f"{DependentPluginProvider.__module__}:{DependentPluginProvider.__name__}",
            group="mcmr.providers",
        ),
    )
    monkeypatch.setattr(
        "mcmr.execution.providers.evidence.metadata.entry_points",
        lambda **selection: entries,
    )
    monkeypatch.setattr(DependentPluginProvider, "families", {PluginFact: {DependencyFact}})
    monkeypatch.setattr(DependencyProvider, "families", {DependencyFact: {PluginFact}})

    with pytest.raises(RuntimeError, match="dependency cycle includes dependencies, dependent"):
        await ExternalEvidence.for_repository(tmp_path).tables({PluginFact})


@pytest.mark.anyio
async def test_table_judgment_materializes_native_provider_dependencies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Native tables requested only by a provider enter the same request-local graph."""
    rule, definition, native_rule, native_definition = dependency_rules()
    functions = fact_table(FunctionFact, [])
    session = module_session(("FunctionFact",), functions)
    monkeypatch.setattr(
        sys.modules[TableExecution.__module__],
        "AnalysisSession",
        lambda *arguments, **keywords: session,
    )
    monkeypatch.setattr(DependencyProvider, "families", {DependencyFact: {FunctionFact}})

    async def collect(
        provider: DependencyProvider,
        context: ProviderContext,
    ) -> list[Fact]:
        assert provider.families[DependencyFact] == {FunctionFact}
        assert context.table(FunctionFact) is functions
        return [DependencyFact(key="dependencies", span=SourceSpan(path="pyproject.toml"))]

    monkeypatch.setattr(DependencyProvider, "collect", collect)
    engine = RuleEngine(rules=[rule, native_rule])

    coverage = await TableExecution(
        root=tmp_path,
        suffixes=(),
        dependencies=engine.dependencies,
        accumulator=JudgmentAccumulator(
            RulePolicies(),
            (definition, native_definition),
            failure_limit=None,
        ),
    ).run(
        {DependencyFact, FunctionFact},
        batches=engine.batches,
        fix_counts=engine.fix_counts,
    )

    assert (coverage.runnable, coverage.provider_read_count) == ({definition.callable}, 2)


@pytest.mark.anyio
async def test_table_judgment_rejects_an_unavailable_provider_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider dependencies must be owned externally or buildable by the native graph."""
    monkeypatch.setattr(DependencyProvider, "families", {DependencyFact: {AlertFact}})
    accumulator = JudgmentAccumulator(RulePolicies(), (), failure_limit=None)

    with pytest.raises(RuntimeError, match="unavailable families AlertFact"):
        await TableExecution(
            root=tmp_path,
            suffixes=(),
            dependencies={},
            accumulator=accumulator,
        ).run(
            {DependencyFact},
            batches=(),
            fix_counts={},
        )
