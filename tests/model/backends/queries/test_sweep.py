from typing import TYPE_CHECKING

import polars as pl
import pytest
from pydantic import ValidationError

from mcmr.contextual.evaluation import (
    ContextualSweep,
    ContextualSweepReport,
    ContextualSweepResult,
)
from mcmr.domain.contracts import (
    Criterion,
    ModelProvenance,
    RuleContract,
    RuleDependency,
    RuleSetting,
    Unit,
)
from mcmr.execution import Assessment, CriterionAnswer, CriterionValue
from mcmr.execution.queries import AssessmentContract, ModelQuery, answer_frame
from mcmr.facts import Fact
from mcmr.query import FixQuery, RuleQuery
from mcmr.query.runtime import QueryEvaluations
from mcmr.rulebook.catalog import Catalog
from mcmr.rulebook.discovery import RuleModuleDiscovery
from mcmr.table import GenericRelation, Table

from ...backend_fakes import Category, FirstCategoryBackend, NoFindingsBackend
from ...backend_values import provenance

if TYPE_CHECKING:
    from collections.abc import Mapping


@pytest.mark.anyio
async def test_the_contextual_sweep_executes_every_model_rule() -> None:
    catalog = Catalog(modules=RuleModuleDiscovery().modules)
    report = await ContextualSweep(backend=FirstCategoryBackend(), workers=4).run(catalog, {})

    assert (
        len(report.results),
        len({result.rule for result in report.results}),
        all(result.finding_count for result in report.results),
        report.input_tokens,
        report.cached_input_tokens,
        report.output_tokens,
        report.reasoning_tokens,
        report.error_count,
    ) == (45, 45, True, 0, 0, 0, 0, 0)
    assert report.elapsed_seconds >= 0
    assert report.message_characters > 0


@pytest.mark.anyio
async def test_the_contextual_sweep_retains_an_isolated_backend_failure() -> None:
    catalog = Catalog(modules=RuleModuleDiscovery().modules)

    async def fail(self: FirstCategoryBackend, query: ModelQuery) -> RuleQuery:
        del self, query
        raise ValueError("model cited unknown evidence")

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(FirstCategoryBackend, "resolve", fail)
        report = await ContextualSweep(backend=FirstCategoryBackend()).run(catalog, {})

    assert report.error_count == 45
    assert all(result.value == "error" for result in report.results)
    assert all(result.provenance.model == "unknown" for result in report.results)
    assert all("unknown evidence" in result.error for result in report.results)


@pytest.mark.anyio
async def test_the_contextual_sweep_requires_one_model_query_per_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = Catalog(modules=RuleModuleDiscovery().modules)

    def deterministic_query(
        self: RuleContract,
        subject: Table[Fact],
        *,
        settings: Mapping[str, RuleSetting],
        dependencies: Mapping[type, RuleDependency],
    ) -> RuleQuery[bool]:
        del self, subject, settings, dependencies
        return RuleQuery.boolean(
            ContextualSweep.table(Fact, "ALL-DEMO2001").lazy(GenericRelation.FACTS),
            pl.lit(False),
        )

    monkeypatch.setattr(type(catalog.rules[0]), "invoke_table", deterministic_query)
    with pytest.raises(TypeError, match="did not return a model query"):
        await ContextualSweep(backend=FirstCategoryBackend()).run(catalog, {})


@pytest.mark.anyio
async def test_the_contextual_sweep_requires_model_provenance() -> None:
    catalog = Catalog(modules=RuleModuleDiscovery().modules)
    with pytest.raises(ValueError, match="returned no model provenance"):
        await ContextualSweep(backend=NoFindingsBackend()).run(catalog, {})


def test_table_failure_reconstruction_rejoins_contextual_findings_by_rule_and_fact() -> None:
    failures = pl.DataFrame(
        {
            "rule": ["mcmr.rules.demo.r2001.example"],
            "fact_id": ["design:shop/service.py"],
            "path": ["shop/service.py"],
            "start_line": pl.Series([4], dtype=pl.UInt64),
            "start_column": pl.Series([0], dtype=pl.UInt64),
            "end_line": pl.Series([12], dtype=pl.UInt64),
            "end_column": pl.Series([0], dtype=pl.UInt64),
            "integer_value": pl.Series([None], dtype=pl.UInt64),
            "boolean_value": pl.Series([None], dtype=pl.Boolean),
            "float_value": pl.Series([None], dtype=pl.Float64),
            "category_value": ["supported"],
        }
    )
    findings = pl.DataFrame(
        {
            "rule": ["mcmr.rules.demo.r2001.example"],
            "fact_id": ["design:shop/service.py"],
            "message": ["The retained structure supports this classification."],
            "path": ["shop/service.py"],
            "start_line": pl.Series([4], dtype=pl.UInt64),
            "start_column": pl.Series([0], dtype=pl.UInt64),
            "end_line": pl.Series([12], dtype=pl.UInt64),
            "end_column": pl.Series([0], dtype=pl.UInt64),
            "measurement_names": [["model confidence"]],
            "measurement_values": [[75.0]],
            "measurement_units": [["percentage"]],
            "evidence": [["structure"]],
            "choice_question": [""],
            "choice_options": [[]],
            "provenance_backend": ["controlled"],
            "provenance_model": ["test"],
            "provenance_reasoning_effort": ["none"],
            "provenance_input_tokens": [0],
            "provenance_cached_input_tokens": [0],
            "provenance_output_tokens": [0],
            "provenance_reasoning_tokens": [0],
        }
    )
    evaluations = QueryEvaluations(
        failures=failures,
        findings=findings,
        fix_rewrites=FixQuery.empty_rewrites().collect(),
        fix_nodes=FixQuery.empty_nodes().collect(),
        fix_imports=FixQuery.empty_imports().collect(),
    )
    finding = next(evaluations.evaluations()).findings[0]
    assert finding.evidence == ["structure"]
    assert finding.measurements[0].unit is Unit.PERCENTAGE
    assert finding.provenance == provenance()


def test_a_contextual_sweep_report_cannot_be_empty_or_run_backwards() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        ContextualSweepReport(results=[], elapsed_seconds=0)
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        ContextualSweepReport(
            results=[
                ContextualSweepResult(
                    rule="ALL-DEMO2001",
                    value="uncertain",
                    finding_count=0,
                    provenance=ModelProvenance(
                        backend="controlled", model="test", reasoning_effort="none"
                    ),
                )
            ],
            elapsed_seconds=-1,
        )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (CriterionValue.YES, Category.SUPPORTED),
        (CriterionValue.NO, Category.UNCERTAIN),
        (CriterionValue.UNKNOWN, Category.UNCERTAIN),
    ],
)
def test_the_decision_table_handles_match_default_and_unknown_without_model_policy(
    value: CriterionValue,
    expected: Category,
) -> None:
    table = ((Category.SUPPORTED, (("supported", CriterionValue.YES),)),)
    query = ModelQuery.assess(
        ContextualSweep.table(Fact, "ALL-DEMO2001"),
        contract=AssessmentContract(
            criteria=[Criterion(name="supported", question="Is it supported?")],
            instructions="Assess support.",
            decision_table=table,
            default=Category.UNCERTAIN,
            uncertain=Category.UNCERTAIN,
        ),
    )
    candidates = query.candidates.collect()
    answers = answer_frame(
        query,
        rows=candidates.to_dicts(),
        outcomes=[
            Assessment(
                answers=[
                    CriterionAnswer(
                        criterion="supported",
                        value=value,
                        reasoning="Controlled predicate answer.",
                        evidence=["fact:sweep:ALL-DEMO2001"],
                        confidence=1.0,
                        provenance=provenance(),
                    )
                ]
            )
        ],
    )
    resolved = query.resolved(candidates, answers=answers)
    assert resolved.values.collect().item(0, "category_value") == expected
