from enum import StrEnum
from typing import TYPE_CHECKING

import polars as pl
import pytest

from mcmr import Boolean, Category
from mcmr.contextual.evaluation import ContextualSweep
from mcmr.domain.contracts import Criterion, ModelProvenance, fact_type
from mcmr.execution import (
    Assessment,
    Classification,
    ClassificationBackend,
    CriterionAnswer,
    CriterionValue,
    ModelCandidate,
)
from mcmr.execution.queries import AssessmentContract, ModelMode, ModelQuery
from mcmr.plugins import Fact, Table
from mcmr.table import GenericRelation

from ..support import built_catalog
from .fakes import LabeledBackend

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


def _classification() -> ModelQuery[CriterionValue]:
    """One contextual classification over the sparse demonstration candidate."""
    return ModelQuery.classify(
        ContextualSweep.table(Fact, "ALL-DEMO2001"),
        category=CriterionValue,
        instructions="Classify support.",
    )


@pytest.mark.anyio
async def test_a_classification_states_what_selecting_each_category_reports() -> None:
    """The model is told the effect of each label, since a name alone never carries it."""
    policy = Category.outcomes(
        CriterionValue,
        good={CriterionValue.YES},
        neutral={CriterionValue.UNKNOWN},
    )
    judged = _classification().judged(policy.reported(CriterionValue))
    backend = LabeledBackend(classification_value=str(CriterionValue.YES))
    findings = (await backend.resolve(judged)).findings
    assert findings is not None

    assert judged.reported == {
        "yes": "reports nothing and records the subject as acceptable",
        "no": "reports the subject as a defect for someone to fix",
        "unknown": "reports nothing and leaves the subject unjudged",
    }
    assert judged.stated_instructions.startswith("Classify support.")
    assert "`no` reports the subject as a defect" in judged.stated_instructions
    assert "rather than the one whose report you would prefer" in judged.stated_instructions
    assert findings.rows.collect().get_column("message").to_list() == [judged.stated_instructions]


def test_an_unjudged_query_keeps_the_instructions_the_rule_wrote() -> None:
    """A policy that judges none of the categories, or an assessment, says nothing extra."""
    judging = Category.outcomes(CriterionValue, good={CriterionValue.YES})
    assess = ModelQuery[CriterionValue](
        candidates=ContextualSweep.table(Fact, "ALL-DEMO2001").lazy(GenericRelation.FACTS),
        category=CriterionValue,
        instructions="Assess support.",
        mode=ModelMode.ASSESS,
    )

    assert Boolean().reported(CriterionValue) == {}
    assert Category(good={"elsewhere"}).reported(CriterionValue) == {}
    assert assess.judged(judging.reported(CriterionValue)).reported == {}
    assert _classification().judged({}).stated_instructions == "Classify support."


def test_invalid_direct_assessment_construction_fails_before_reduction() -> None:
    query = ModelQuery[CriterionValue](
        candidates=ContextualSweep.table(Fact, "ALL-DEMO2001").lazy(GenericRelation.FACTS),
        category=CriterionValue,
        instructions="Assess support.",
        mode=ModelMode.ASSESS,
    )

    with pytest.raises(TypeError, match="needs default and uncertainty"):
        query.resolved(query.candidates.collect(), answers=pl.DataFrame())


_CASES: list[tuple[str, dict[str, CriterionValue], str]] = [
    ("ALL-DEPL1001", {}, "verified"),
    ("ALL-DEPL1001", {"progressive rollout needed": _NO}, "not_needed"),
    ("ALL-DEPL1001", {"outcomes decide": _UNKNOWN}, "uncertain"),
    ("ALL-DEPL1002", {}, "controlled"),
    ("ALL-DEPL1002", {"traffic limit enforced": _NO}, "unbounded"),
    ("ALL-DEPL1002", {"halt works": _UNKNOWN}, "uncertain"),
    ("ALL-DEPL1003", {}, "decisive"),
    ("ALL-DEPL1003", {"criteria exist": _NO}, "absent"),
    ("ALL-DEPL1003", {"comparison is explicit": _UNKNOWN}, "uncertain"),
    ("ALL-DEPL1004", {}, "ready"),
    ("ALL-DEPL1004", {"representative rehearsal passed": _NO}, "unverified"),
    ("ALL-DEPL1004", {"steps are owned and timely": _UNKNOWN}, "uncertain"),
    ("ALL-RELI1003", {}, "bounded"),
    ("ALL-RELI1003", {"input naturally finite": _NO}, "backpressured"),
    ("ALL-RELI1003", {"resources bounded": _UNKNOWN}, "uncertain"),
    ("ALL-STRI1001", {}, "jinja2"),
    ("ALL-STRI1001", {"template semantics": _NO}, "f_string_join"),
    ("ALL-STRI1001", {"python iteration": _UNKNOWN}, "uncertain"),
    ("ALL-DESI1001", {}, "modeled"),
    ("ALL-DESI1001", {"domain rules repeat": _NO}, "overmodeled"),
    ("ALL-DESI1001", {"one value owns meaning": _UNKNOWN}, "uncertain"),
]


@pytest.mark.anyio
@pytest.mark.parametrize(("rule_id", "values", "expected"), _CASES)
async def test_model_predicates_reduce_without_asking_for_the_final_category(
    rule_id: str,
    values: dict[str, CriterionValue],
    expected: str,
) -> None:
    candidate = next(rule for rule in built_catalog().rules if rule.id == rule_id)
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

    assert answer.findings is not None
    finding_frame = answer.findings.normalized().rows.collect()
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
