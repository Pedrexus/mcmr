from typing import TYPE_CHECKING

import pytest

from mcmr import MCMRConfiguration, RulePolicies
from mcmr.checking.engine import RuleEngine
from mcmr.commands.quality import Judgment
from mcmr.facts import FunctionFact
from mcmr.plugins import RepositoryTables
from mcmr.query.runtime import TableRunner
from mcmr.table import AnalysisSession, FunctionRelation

from ...support import built_catalog, kernel_binary, needs_kernel

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from mcmr.checking.evaluations import PreparedRule, TableEvaluationReport
    from mcmr.domain.contracts import RuleContract, RuleSetting
    from mcmr.domain.policy import Policy


def repository(root: Path) -> Path:
    """Write a mixed-language corpus covering function table rules in both directions."""
    (root / "service.py").write_text(
        """import asyncio
from functools import cache, cached_property

from pydantic import BaseModel


class Configuration(BaseModel):
    value: int

    @classmethod
    def from_value(cls, raw: object) -> "Configuration":
        if not isinstance(raw, int):
            raise ValueError("value must be an integer")
        return cls(value=raw)


def flat(optional: int = 1) -> int:
    return optional


def nested(required: int, enabled: bool) -> int:
    if enabled:
        for value in range(required):
            if value:
                return value
    return 0


def _obsolete() -> int:
    return 1


def _double(value: int) -> int:
    return value * 2


def use_double(value: int) -> int:
    return _double(value)


def normalize(value: int) -> int:
    return int(value)


def use_normalize(value: int) -> int:
    return normalize(value)


def outer(value: int) -> int:
    def inner(item: int) -> int:
        return item + 1

    return inner(value)


async def work() -> int:
    return 1


async def concurrent() -> list[int]:
    task = asyncio.create_task(work())
    return await asyncio.gather(task)


class Cache:
    @cached_property
    def version(self) -> int:
        return 1

    @cache
    def compute(self, value: int) -> int:
        return value
""",
        encoding="utf-8",
    )
    (root / "choice.rs").write_text(
        """fn choose(enabled: bool, ready: bool) -> i32 {
    if enabled {
        if ready {
            return 1;
        }
    }
    0
}
""",
        encoding="utf-8",
    )
    return root


def all_function_rules() -> list[RuleContract]:
    """Return every deterministic FunctionFact rule in catalog order."""
    catalog = built_catalog()
    paths = {
        definition.callable
        for definition in catalog.definitions
        if definition.fact == FunctionFact.__name__ and definition.lane == "deterministic"
    }
    return [rule for rule in catalog.rules if rule.callable_path in paths]


def policies(rules: Sequence[PreparedRule]) -> dict[str, Policy | None]:
    """Return the configured policy selected for every prepared function rule."""
    configured = RulePolicies()
    definitions = {definition.callable: definition for definition in built_catalog().definitions}
    return {
        rule.path: configured.policy(
            rule_id=definitions[rule.path].id,
            candidate=definitions[rule.path].policy,
        )
        for rule in rules
    }


async def report(
    session: AnalysisSession,
    engine: RuleEngine,
    failure_limit: int | None = None,
) -> TableEvaluationReport:
    """Run the complete function query graph once without a row fallback."""
    tables = RepositoryTables()
    tables.add(session.function_tables())
    return await TableRunner(engine.dependencies).report(
        tables,
        engine.prepared,
        policies=policies(engine.prepared),
        fix_counts=engine.fix_counts,
        failure_limit=failure_limit,
    )


@pytest.mark.anyio
async def test_complete_function_plan_executes_every_rule_once(tmp_path: Path) -> None:
    session = AnalysisSession(
        repository(tmp_path),
        suffixes=[".py", ".rs"],
        typed_families=[FunctionFact],
    )
    engine = RuleEngine(rules=all_function_rules())
    prepared = engine.prepared
    result = await report(session, engine)
    functions = (
        AnalysisSession(
            repository(tmp_path),
            suffixes=[".py", ".rs"],
            typed_families=[FunctionFact],
        )
        .function_tables()
        .frame(FunctionRelation.FUNCTIONS)
    )
    python_count = functions.filter(functions["language"] == "python").height
    scopes = {rule.path: str(rule.scope) for rule in prepared}

    assert (
        len(result.summaries),
        result.stats.rule_execution_count,
        result.stats.table_query_count,
        result.stats.table_queries_by_family,
        result.stats.fact_count,
        hasattr(result.stats, "row_call_count"),
    ) == (
        len(prepared),
        len(prepared),
        len(prepared),
        {FunctionFact.__name__: len(prepared)},
        functions.height,
        False,
    )
    assert {summary.rule: summary.observation_count for summary in result.summaries} == {
        rule.path: result.stats.fact_count if scopes[rule.path] == "general" else python_count
        for rule in prepared
    }


@pytest.mark.anyio
async def test_function_plan_rejects_a_result_outside_the_query_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rule = all_function_rules()[0]
    engine = RuleEngine(rules=[rule])
    prepared = engine.prepared
    session = AnalysisSession(
        repository(tmp_path),
        suffixes=[".py", ".rs"],
        typed_families=[FunctionFact],
    )
    monkeypatch.setattr(
        type(rule),
        "invoke",
        lambda self, tables, *, settings, dependencies, languages: False,
    )

    with pytest.raises(TypeError, match="returned bool instead of a query"):
        tables = RepositoryTables()
        tables.add(session.function_tables())
        await TableRunner(engine.dependencies).report(
            tables,
            prepared,
            policies=policies(prepared),
            fix_counts=engine.fix_counts,
            failure_limit=None,
        )


@pytest.mark.anyio
async def test_function_plan_preserves_settings_exclusions_and_findings(tmp_path: Path) -> None:
    selected = all_function_rules()
    by_name = {rule.qualname: rule.callable_path for rule in selected}
    settings: dict[str, dict[str, RuleSetting]] = {
        by_name["single_use_trivial_helper"]: {
            "maximum_lines": 0,
            "ignore_names": ["_obsolete"],
        },
        by_name["cognitive_complexity"]: {"nesting_penalty": 2},
        by_name["compact_house_docstring"]: {"maximum_summary": 20},
    }
    engine = RuleEngine(
        rules=selected,
        settings=settings,
        exclusions={rule.callable_path: ("service.py",) for rule in selected},
    )
    result = await report(
        AnalysisSession(
            repository(tmp_path),
            suffixes=[".py", ".rs"],
            typed_families=[FunctionFact],
        ),
        engine,
    )
    failures = list(result.failures)

    assert failures
    assert {failure.span.path for failure in failures} == {"choice.rs"}
    assert all(not failure.rule.startswith("mcmr.rules.python") for failure in failures)
    assert not hasattr(result.stats, "row_call_count")


@pytest.mark.anyio
async def test_function_plan_keeps_fix_rows_and_failure_order(tmp_path: Path) -> None:
    result = await report(
        AnalysisSession(
            repository(tmp_path),
            suffixes=[".py", ".rs"],
            typed_families=[FunctionFact],
        ),
        RuleEngine(rules=all_function_rules()),
    )
    failures = list(result.failures)
    findings = [finding for failure in failures for finding in failure.findings]

    assert failures
    assert any(finding.repair is not None for finding in findings)
    assert list(dict.fromkeys(failure.span.path for failure in failures)) == [
        "choice.rs",
        "service.py",
    ]


@needs_kernel
def test_complete_function_judgment_uses_only_table_queries(tmp_path: Path) -> None:
    root = repository(tmp_path)
    selection = [
        definition.id
        for definition in built_catalog().definitions
        if definition.fact == FunctionFact.__name__ and definition.lane == "deterministic"
    ]
    judged = Judgment(
        binary=kernel_binary(),
        root=root,
        policies=RulePolicies(),
        suffixes=(".py", ".rs"),
        configuration=MCMRConfiguration(select=selection),
    ).run()

    assert judged.engine.rule_execution_count == len(selection)
    assert judged.engine.table_query_count == len(selection)
    assert judged.engine.table_queries_by_family == {FunctionFact.__name__: len(selection)}
    assert not hasattr(judged.engine, "row_call_count")
