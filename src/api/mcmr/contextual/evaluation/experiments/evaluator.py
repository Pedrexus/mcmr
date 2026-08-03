from collections.abc import Sequence
from typing import TYPE_CHECKING

from patos import FrozenModel, Runtime

from ....execution import ClassificationBackend
from ....execution.queries import ModelMode, ModelQuery
from ...corpus import ContextualCase
from ..cases import ContextualTrial
from ..profiles import BackendProfile

if TYPE_CHECKING:
    from enum import StrEnum

    from ....execution import Assessment, Classification


class CaseEvaluator(FrozenModel):
    """Evaluate one rule's reviewed cases through one contextual backend."""

    profile: BackendProfile
    backend: Runtime[ClassificationBackend]
    template: ModelQuery
    cases: Runtime[Sequence[ContextualCase]]

    async def run(self) -> list[ContextualTrial]:
        """Dispatch this batch through its query mode and retain exact comparisons."""
        return (
            await self._classify()
            if self.template.mode is ModelMode.CLASSIFY
            else await self._assess()
        )

    async def _assess(self) -> list[ContextualTrial]:
        """Evaluate a criterion query and retain one trial per case."""
        try:
            answers = await self.backend.assess_many(
                [case.candidate for case in self.cases],
                criteria=self.template.criteria,
                instructions=self.template.instructions,
            )
        except Exception as failure:
            return self._failed(failure)
        if len(answers) != len(self.cases):
            return self._failed(
                ValueError("contextual backend returned a different number of answers")
            )
        return [
            self._assessment_trial(case, answer)
            for case, answer in zip(self.cases, answers, strict=True)
        ]

    def _assessment_trial(self, case: ContextualCase, assessment: Assessment) -> ContextualTrial:
        """Convert one criterion assessment into an exact labeled trial."""
        answer = {item.criterion: str(item.value) for item in assessment.answers}
        evidence = dict.fromkeys(
            str(identifier) for item in assessment.answers for identifier in item.evidence
        )
        return ContextualTrial(
            profile=self.profile.name,
            rule=case.rule,
            case=case.name,
            expected=case.expected.rendered(),
            actual=answer,
            passed=case.expected.rendered() == answer,
            reasoning=[item.reasoning for item in assessment.answers],
            evidence_ids=list(evidence),
            provenance=assessment.answers[0].provenance if assessment.answers else None,
        )

    def _classification_trial(
        self,
        case: ContextualCase,
        classification: Classification[StrEnum],
    ) -> ContextualTrial:
        """Convert one categorical answer into an exact labeled trial."""
        actual = str(classification.value)
        return ContextualTrial(
            profile=self.profile.name,
            rule=case.rule,
            case=case.name,
            expected=case.expected.rendered(),
            actual=actual,
            passed=case.expected.rendered() == actual,
            reasoning=[classification.reasoning],
            evidence_ids=[str(identifier) for identifier in classification.evidence],
            provenance=classification.provenance,
        )

    async def _classify(self) -> list[ContextualTrial]:
        """Evaluate a categorical query and retain one trial per case."""
        try:
            answers = await self.backend.classify_many(
                [case.candidate for case in self.cases],
                category=self.template.category,
                instructions=self.template.instructions,
            )
        except Exception as failure:
            return self._failed(failure)
        if len(answers) != len(self.cases):
            return self._failed(
                ValueError("contextual backend returned a different number of answers")
            )
        return [
            self._classification_trial(case, answer)
            for case, answer in zip(self.cases, answers, strict=True)
        ]

    def _failed(self, failure: Exception) -> list[ContextualTrial]:
        """Turn one backend failure into explicit failed trials for its whole batch."""
        return [
            ContextualTrial(
                profile=self.profile.name,
                rule=case.rule,
                case=case.name,
                expected=case.expected.rendered(),
                error=f"{type(failure).__name__}: {failure}",
            )
            for case in self.cases
        ]
