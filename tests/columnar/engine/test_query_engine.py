from enum import StrEnum
from typing import TYPE_CHECKING, cast

import polars as pl
import pytest

from mcmr import Category, Numeric
from mcmr.checking.evaluations import PreparedRule
from mcmr.domain.contracts import ModelProvenance
from mcmr.execution import Classification, ClassificationBackend, ModelCandidate
from mcmr.facts import FunctionFact
from mcmr.plugins import RepositoryTables
from mcmr.query import FixQuery, RuleQuery
from mcmr.query.runtime import (
    CollectedRules,
    RuleCompiler,
    TableRunner,
)
from mcmr.rules.general import AbstractionLevel, abstraction_level
from mcmr.table import AnalysisSession

if TYPE_CHECKING:
    from pathlib import Path


class ControlledBackend(ClassificationBackend):
    """Return the first allowed category with auditable model evidence."""

    async def classify_candidate[Answer: StrEnum](
        self,
        candidate: ModelCandidate,
        *,
        category: type[Answer],
        instructions: str,
    ) -> Classification[Answer]:
        """Resolve one candidate without an external model process."""
        assert instructions
        return Classification(
            value=next(iter(category)),
            reasoning="Controlled classification for the table runner.",
            evidence=list(candidate.retained)[:8],
            confidence=1.0,
            provenance=ModelProvenance(
                backend="controlled",
                model="test",
                reasoning_effort="none",
            ),
        )


def prepared(contract: tuple[str, str, list[str]]) -> PreparedRule:
    """Build one prepared rule for compiler and runner contract tests."""
    return PreparedRule.of(abstraction_level, contract, {}, ())


def test_compiler_keeps_a_query_without_findings_unassessed() -> None:
    source = pl.DataFrame(
        {
            "fact_order": pl.Series([0], dtype=pl.UInt64),
            "fact_id": ["function:subject.py:answer"],
            "path": ["subject.py"],
            "language": ["python"],
            "start_line": pl.Series([1], dtype=pl.UInt64),
            "start_column": pl.Series([0], dtype=pl.UInt64),
            "end_line": pl.Series([2], dtype=pl.UInt64),
            "end_column": pl.Series([0], dtype=pl.UInt64),
        }
    ).lazy()
    query = RuleQuery.boolean(source, pl.lit(True))

    result = (
        RuleCompiler(
            prepared=prepared(("bool", "count", [])),
            query=cast("RuleQuery", query),
            policy=None,
            accepted_paths=["subject.py"],
            rule_order=0,
        )
        .compile()
        .result.collect()
    )

    assert result.item(0, "observation_count") == 1
    assert result.item(0, "unassessed_count") == 1
    assert result.item(0, "failure_count") == 0


def test_compiler_rejects_a_fix_without_rule_owned_safety() -> None:
    """Repair safety belongs to the rule contract rather than the emitted query."""
    source = pl.DataFrame(
        {
            "fact_order": pl.Series([0], dtype=pl.UInt64),
            "fact_id": ["function:subject.py:answer"],
            "path": ["subject.py"],
            "language": ["python"],
            "start_line": pl.Series([1], dtype=pl.UInt64),
            "start_column": pl.Series([0], dtype=pl.UInt64),
            "end_line": pl.Series([1], dtype=pl.UInt64),
            "end_column": pl.Series([1], dtype=pl.UInt64),
        }
    ).lazy()
    query = RuleQuery.boolean(
        source,
        pl.lit(True),
        fix=FixQuery.build("Repair the subject.", rewrites=FixQuery.empty_rewrites()),
    )

    with pytest.raises(TypeError, match="declare repair safety exactly"):
        RuleCompiler(
            prepared=prepared(("bool", "count", [])),
            query=cast("RuleQuery", query),
            policy=None,
            accepted_paths=["subject.py"],
            rule_order=0,
        ).compile()


def test_numeric_minimum_compiles_as_a_lower_bound() -> None:
    failed, unassessed = RuleCompiler.verdict(Numeric(minimum=2), "int")
    result = pl.DataFrame({"integer_value": [1]}).select(
        failed.alias("failed"),
        unassessed.alias("unassessed"),
    )

    assert result.item(0, "failed")
    assert not result.item(0, "unassessed")


def test_empty_compilation_collects_empty_relations() -> None:
    collected = CollectedRules.collect((), None)

    assert collected.summaries.is_empty()
    assert collected.failures.is_empty()
    assert collected.findings.is_empty()
    assert collected.fix_rewrites.is_empty()
    assert collected.fix_nodes.is_empty()
    assert collected.fix_imports.is_empty()


@pytest.mark.anyio
async def test_table_runner_selects_and_resolves_one_model_query(tmp_path: Path) -> None:
    (tmp_path / "subject.py").write_text(
        """def answer(value: int) -> int:
    normalized = abs(value)
    doubled = max(normalized * 2, 1)
    rendered = str(doubled)
    cleaned = rendered.strip()
    parsed = int(cleaned)
    return parsed
""",
        encoding="utf-8",
    )
    table = AnalysisSession(
        tmp_path,
        suffixes=[".py"],
        typed_families=[FunctionFact],
    ).function_tables()
    rule = prepared(("str", "", [str(item) for item in AbstractionLevel]))
    tables = RepositoryTables()
    tables.add(table)
    report = await TableRunner({ClassificationBackend: ControlledBackend()}).report(
        tables,
        (rule,),
        policies={
            rule.path: Category(
                good={str(AbstractionLevel.MIXED)},
                bad={str(AbstractionLevel.COHESIVE)},
            )
        },
        fix_counts={rule.path: 0},
        failure_limit=None,
    )

    failure = next(iter(report.failures))
    assert failure.value == str(AbstractionLevel.COHESIVE)
    assert failure.findings[0].provenance is not None
    assert failure.findings[0].provenance.backend == "controlled"
