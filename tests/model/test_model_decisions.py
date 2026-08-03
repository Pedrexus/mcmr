from enum import StrEnum
from typing import TYPE_CHECKING

import polars as pl
import pytest

from mcmr.contextual.evaluation import ContextualSweep
from mcmr.domain.contracts import Criterion, ModelProvenance, RuleContract, fact_type
from mcmr.execution import (
    Assessment,
    Classification,
    ClassificationBackend,
    CriterionAnswer,
    CriterionValue,
    ModelCandidate,
)
from mcmr.execution.queries import AssessmentContract, ModelMode, ModelQuery
from mcmr.facts import Fact
from mcmr.rules.general import (
    bounded_work,
    exposure_control,
    primitive_obsession,
    progressive_rollout,
    rollback_readiness,
    rollout_success_criteria,
    string_construction_mechanism,
)
from mcmr.table import GenericRelation, Table

if TYPE_CHECKING:
    from collections.abc import Sequence

_NO = CriterionValue.NO
_UNKNOWN = CriterionValue.UNKNOWN


class FixedCriteria(ClassificationBackend):
    """Return named predicate values while refusing final-category classification."""

    values: dict[str, CriterionValue] = {}
    calls: list[str] = []

    async def assess_candidate(
        self,
        candidate: ModelCandidate,
        *,
        criteria: Sequence[Criterion],
        instructions: str,
    ) -> Assessment:
        assert instructions
        self.calls.append(candidate.fact_id)
        return Assessment(
            answers=[
                CriterionAnswer(
                    criterion=criterion.name,
                    value=self.values.get(criterion.name, CriterionValue.YES),
                    reasoning="Controlled predicate answer.",
                    evidence=list(candidate.retained),
                    confidence=1.0,
                    provenance=ModelProvenance(
                        backend="controlled",
                        model="test",
                        reasoning_effort="none",
                    ),
                )
                for criterion in criteria
            ]
        )

    async def classify_candidate[Category: StrEnum](
        self,
        candidate: ModelCandidate,
        *,
        category: type[Category],
        instructions: str,
    ) -> Classification[Category]:
        raise AssertionError(
            "A fixed decision table must not ask the model for its final category"
        )


def test_model_query_rejects_a_table_without_a_contextual_projection() -> None:
    unsupported = StrEnum("UnsupportedRelation", {"FACTS": "facts"})
    frames: dict[StrEnum, pl.DataFrame] = {
        unsupported.FACTS: pl.DataFrame(schema={"language": pl.String})
    }
    table = Table[Fact](
        family=Fact,
        relation_type=unsupported,
        frames=frames,
    )

    with pytest.raises(TypeError, match="Fact has no contextual candidate projection"):
        ModelQuery.candidate_relation(table)


def test_model_assessment_rejects_empty_and_duplicate_criteria() -> None:
    subject = ContextualSweep.table(Fact, "ALL-DEMO2001")
    criterion = Criterion(name="supported", question="Is it supported?")

    with pytest.raises(ValueError, match="at least one criterion"):
        ModelQuery.assess(
            subject,
            contract=AssessmentContract(
                criteria=[],
                instructions="Assess support.",
                decision_table=[],
                default=CriterionValue.NO,
                uncertain=CriterionValue.UNKNOWN,
            ),
        )
    with pytest.raises(ValueError, match="must be unique"):
        ModelQuery.assess(
            subject,
            contract=AssessmentContract(
                criteria=[criterion, criterion],
                instructions="Assess support.",
                decision_table=[],
                default=CriterionValue.NO,
                uncertain=CriterionValue.UNKNOWN,
            ),
        )


def test_model_query_selection_and_fixed_choice_question_are_relational() -> None:
    subject = ContextualSweep.table(Fact, "ALL-DEMO2001")
    query = ModelQuery.classify(
        subject,
        category=CriterionValue,
        instructions="Classify support.",
    )
    path = "contextual/ALL-DEMO2001.json"

    assert (
        query.selected([path], language=None).candidates.collect().height,
        query.selected([path], language="general").candidates.collect().height,
        query.selected([path], language="python").candidates.collect().height,
        query.matching(pl.LazyFrame({"fact_id": ["sweep:ALL-DEMO2001"]}))
        .candidates.collect()
        .height,
        query.matching(pl.LazyFrame({"fact_id": ["other"]})).candidates.collect().height,
    ) == (1, 1, 0, 1, 0)
    with pytest.raises(TypeError, match="missing fact_id"):
        query.matching(pl.LazyFrame({"candidate": ["other"]}))
    with pytest.raises(TypeError, match="contextual projection is missing missing"):
        query.project(query.candidates, fields=("missing",))
    fixed = query.choice("Choose the repair", ("replace", "retain"))
    assert (fixed.choice_question, fixed.choice_options) == (
        "Choose the repair",
        ["replace", "retain"],
    )


def test_invalid_direct_assessment_construction_fails_before_reduction() -> None:
    query = ModelQuery[CriterionValue](
        candidates=ContextualSweep.table(Fact, "ALL-DEMO2001").lazy(GenericRelation.FACTS),
        category=CriterionValue,
        instructions="Assess support.",
        mode=ModelMode.ASSESS,
    )

    with pytest.raises(TypeError, match="needs default and uncertainty"):
        query.resolved(query.candidates.collect(), answers=pl.DataFrame())


_CASES: list[tuple[RuleContract, dict[str, CriterionValue], str]] = [
    (progressive_rollout, {}, "verified"),
    (progressive_rollout, {"progressive rollout needed": _NO}, "not_needed"),
    (progressive_rollout, {"outcomes decide": _UNKNOWN}, "uncertain"),
    (exposure_control, {}, "controlled"),
    (exposure_control, {"traffic limit enforced": _NO}, "unbounded"),
    (exposure_control, {"halt works": _UNKNOWN}, "uncertain"),
    (rollout_success_criteria, {}, "decisive"),
    (rollout_success_criteria, {"criteria exist": _NO}, "absent"),
    (rollout_success_criteria, {"comparison is explicit": _UNKNOWN}, "uncertain"),
    (rollback_readiness, {}, "ready"),
    (rollback_readiness, {"representative rehearsal passed": _NO}, "unverified"),
    (rollback_readiness, {"steps are owned and timely": _UNKNOWN}, "uncertain"),
    (bounded_work, {}, "bounded"),
    (bounded_work, {"input naturally finite": _NO}, "backpressured"),
    (bounded_work, {"resources bounded": _UNKNOWN}, "uncertain"),
    (string_construction_mechanism, {}, "jinja2"),
    (string_construction_mechanism, {"template semantics": _NO}, "f_string_join"),
    (string_construction_mechanism, {"python iteration": _UNKNOWN}, "uncertain"),
    (primitive_obsession, {}, "modeled"),
    (primitive_obsession, {"domain rules repeat": _NO}, "overmodeled"),
    (primitive_obsession, {"one value owns meaning": _UNKNOWN}, "uncertain"),
]


@pytest.mark.anyio
@pytest.mark.parametrize(("candidate", "values", "expected"), _CASES)
async def test_model_predicates_reduce_without_asking_for_the_final_category(
    candidate: RuleContract,
    values: dict[str, CriterionValue],
    expected: str,
) -> None:
    required = fact_type(candidate.hints[next(iter(candidate.signature.parameters))])
    subject = ContextualSweep.table(
        required,
        candidate.qualname,
    )
    backend = FixedCriteria(values=values)

    query = candidate.invoke_table(
        subject,
        settings={},
        dependencies={ClassificationBackend: backend},
    )
    assert isinstance(query, ModelQuery)
    answer = await backend.resolve(query)
    findings = answer.findings

    assert findings is not None
    finding_frame = findings.normalized().rows.collect()
    assert (
        answer.values.collect().item(0, "category_value"),
        finding_frame.height > 0,
        set(finding_frame.get_column("path")),
        all(
            evidence == [f"fact:sweep:{candidate.qualname}"]
            for evidence in finding_frame.get_column("evidence").to_list()
        ),
        set(finding_frame.get_column("provenance_backend")),
        backend.calls,
    ) == (
        expected,
        True,
        {f"contextual/{candidate.qualname}.json"},
        True,
        {"controlled"},
        [f"sweep:{candidate.qualname}"],
    )
