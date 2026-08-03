from typing import TYPE_CHECKING

import pytest

from mcmr import MCMRConfiguration, Numeric, RulePolicies
from mcmr.checking.engine import RuleEngine
from mcmr.checking.session import Judgment
from mcmr.query.runtime import TableRunner
from mcmr.table import AnalysisSession, RepositoryTables

from ...support import built_catalog, kernel_binary, needs_kernel

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from mcmr.domain.contracts import RuleContract, RuleSetting


def repository(tmp_path: Path) -> Path:
    """Write one call corpus exercising simple, grouped, recursive, and repair rules."""
    (tmp_path / "subject.py").write_text(
        """import argparse
import asyncio
import logging
import requests
import third_party
import torch
from pydantic import BaseModel
from typing import cast


class User(BaseModel):
    name: str


def work() -> None:
    pass


async def run(flag: bool, value, row) -> None:
    argparse.ArgumentParser()
    asyncio.run(work())
    asyncio.get_event_loop_policy()
    asyncio.iscoroutinefunction(work)
    await asyncio.get_running_loop().run_in_executor(None, len, [1])
    logging.warning("retrying")
    requests.get("https://example.com")
    tuple([1, 2])
    User.model_validate({"name": "Ada"})
    bool(flag)
    value = torch.sqrt(torch.abs(value))
    torch.as_tensor(torch.Tensor.cpu(value))
    third_party.normalize(value)
    third_party.normalize(flag)
    third_party.normalize(row)
    cast(str, row["first"])
    cast(str, row["second"])
    cast(str, row["third"])
"""
    )
    (tmp_path / "kernel.cu").write_text(
        """void run(void *target, void *source, int bytes) {
    cudaStreamCreate();
    cudaMemcpy(target, source, bytes, 0);
    __syncthreads();
}
"""
    )
    return tmp_path


def all_call_rules() -> list[RuleContract]:
    """Return every deterministic CallFact rule in catalog order."""
    catalog = built_catalog()
    paths = {
        definition.callable
        for definition in catalog.definitions
        if definition.fact == "CallFact" and definition.lane == "deterministic"
    }
    return [rule for rule in catalog.rules if rule.callable_path in paths]


def policies(rules: Sequence[RuleContract]) -> dict[str, Numeric]:
    """Fail every positive count so retained evidence is exercised."""
    return {rule.callable_path: Numeric(maximum=0) for rule in rules}


def repository_tables(session: AnalysisSession) -> RepositoryTables:
    """Combine call and function tables from one analysis session."""
    tables = RepositoryTables()
    tables.add(session.call_tables())
    tables.add(session.function_tables())
    return tables


@pytest.mark.anyio
async def test_complete_call_plan_runs_every_rule_once_with_findings_and_repairs(
    tmp_path: Path,
) -> None:
    session = AnalysisSession(
        repository(tmp_path),
        suffixes=[".py", ".cu"],
        typed_families=("CallFact", "FunctionFact"),
    )
    selected = all_call_rules()
    by_name = {rule.qualname: rule.callable_path for rule in selected}
    settings: dict[str, dict[str, RuleSetting]] = {
        by_name["unchecked_result_call"]: {"checked_callables": ["logging.warning"]},
        by_name["unbounded_blocking_call"]: {"bounded_callables": ["requests.get"]},
        by_name["repeated_external_unary_transformation"]: {"minimum_files": 1},
    }
    engine = RuleEngine(rules=selected, settings=settings)

    report = await TableRunner({}).report(
        repository_tables(session),
        engine.prepared,
        policies=policies(selected),
        fix_counts=engine.fix_counts,
        failure_limit=None,
    )
    failures = list(report.failures)

    assert (
        len(report.summaries),
        report.stats.rule_execution_count,
        report.stats.table_query_count,
        report.stats.table_queries_by_family["CallFact"],
        report.stats.observation_count,
        bool(failures),
        any(evaluation.findings for evaluation in failures),
        any(
            finding.repair is not None
            for evaluation in failures
            for finding in evaluation.findings
        ),
    ) == (
        len(selected),
        len(selected),
        len(selected),
        len(selected),
        sum(summary.observation_count for summary in report.summaries),
        True,
        True,
        True,
    )


@pytest.mark.anyio
async def test_call_plan_preserves_exclusions_and_language_scope(tmp_path: Path) -> None:
    session = AnalysisSession(
        repository(tmp_path),
        suffixes=[".py", ".cu"],
        typed_families=("CallFact", "FunctionFact"),
    )
    selected = all_call_rules()
    exclusions = {rule.callable_path: ["subject.py"] for rule in selected}
    engine = RuleEngine(rules=selected, exclusions=exclusions)

    report = await TableRunner({}).report(
        repository_tables(session),
        engine.prepared,
        policies=policies(selected),
        fix_counts=engine.fix_counts,
        failure_limit=None,
    )
    failures = list(report.failures)

    assert {evaluation.span.path for evaluation in failures} == {"kernel.cu"}
    assert all(not evaluation.rule.startswith("mcmr.rules.python") for evaluation in failures)


@needs_kernel
def test_complete_call_judgment_executes_one_query_per_selected_rule(tmp_path: Path) -> None:
    root = repository(tmp_path)
    selection = [
        definition.id
        for definition in built_catalog().definitions
        if definition.fact == "CallFact" and definition.lane == "deterministic"
    ]
    judged = Judgment(
        binary=kernel_binary(),
        root=root,
        policies=RulePolicies(),
        suffixes=(".py", ".cu"),
        configuration=MCMRConfiguration(select=selection),
    ).run()

    assert judged.engine.rule_execution_count == len(selection)
    assert judged.engine.table_query_count == len(selection)
    assert judged.engine.table_queries_by_family == {"CallFact": len(selection)}
    assert judged.engine.fact_count == judged.kernel.fact_count
    assert judged.kernel.file_count == 2


@needs_kernel
def test_one_table_session_combines_all_requested_native_families(tmp_path: Path) -> None:
    root = repository(tmp_path)
    selection = [
        definition.id
        for definition in built_catalog().definitions
        if definition.fact in {"FunctionFact", "CallFact", "ClassFact", "ModuleFact"}
        and definition.lane == "deterministic"
    ]
    judged = Judgment(
        binary=kernel_binary(),
        root=root,
        policies=RulePolicies(),
        suffixes=(".py", ".cu"),
        configuration=MCMRConfiguration(select=selection),
    ).run()

    assert judged.engine.rule_execution_count == len(selection)
    assert judged.engine.table_query_count == len(selection)
    assert judged.engine.provider_read_count == 5
    assert set(judged.engine.table_queries_by_family) == {
        "CallFact",
        "ClassFact",
        "FunctionFact",
        "ModuleFact",
    }
    assert judged.kernel.file_count == 2
