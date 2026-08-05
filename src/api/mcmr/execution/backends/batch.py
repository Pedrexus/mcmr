import json
from enum import StrEnum
from functools import cached_property
from typing import TYPE_CHECKING

from patos import FrozenModel
from pydantic import JsonValue, TypeAdapter

from ...domain.primitives import NonEmptyStr
from ..queries.contracts import Assessment, Classification, ModelCandidate
from .candidate import CandidateProtocol

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from ...domain.contracts import Criterion, ModelProvenance


class BatchProtocol(FrozenModel):
    """Define one evidence-isolated exchange for a bounded candidate batch."""

    candidates: list[ModelCandidate]
    instructions: NonEmptyStr

    @cached_property
    def protocols(self) -> list[CandidateProtocol]:
        """Bind the shared instructions to every isolated candidate."""
        return [
            CandidateProtocol(candidate=candidate, instructions=self.instructions)
            for candidate in self.candidates
        ]

    def assessment_prompt(self, criteria: Sequence[Criterion]) -> str:
        """Render independent candidates with one shared predicate rubric."""
        protocol = self.protocols[0]
        questions = {criterion.name: criterion.question for criterion in criteria}
        return self._prompt(
            protocol.assessment_guidance,
            rubric_name="Criteria",
            rubric=questions,
        )

    def assessment_schema(self, criteria: Sequence[Criterion]) -> dict[str, JsonValue]:
        """Require one complete assessment under every candidate key."""
        return self._schema(self.protocols[0].assessment_schema(criteria))

    def assessments(
        self,
        source: str,
        criteria: Sequence[Criterion],
        provenance: ModelProvenance,
    ) -> list[Assessment]:
        """Validate every independently keyed assessment returned by one turn."""
        return [
            protocol.assessment(answer, criteria, candidate_provenance)
            for protocol, answer, candidate_provenance in zip(
                self.protocols,
                self._answers(source),
                provenance.distribute(len(self.candidates)),
                strict=True,
            )
        ]

    def classification_prompt[Category: StrEnum](self, category: type[Category]) -> str:
        """Render independent candidates with one shared classification rubric."""
        protocol = self.protocols[0]
        categories = {str(item): item.name.lower().replace("_", " ") for item in category}
        return self._prompt(
            protocol.classification_guidance,
            rubric_name="Allowed categories",
            rubric=categories,
        )

    def classification_schema[Category: StrEnum](
        self,
        category: type[Category],
    ) -> dict[str, JsonValue]:
        """Require one complete classification under every candidate key."""
        return self._schema(self.protocols[0].classification_schema(category))

    def classifications[Category: StrEnum](
        self,
        source: str,
        category: type[Category],
        provenance: ModelProvenance,
    ) -> list[Classification[Category]]:
        """Validate every independently keyed classification returned by one turn."""
        return [
            protocol.classification(answer, category, candidate_provenance)
            for protocol, answer, candidate_provenance in zip(
                self.protocols,
                self._answers(source),
                provenance.distribute(len(self.candidates)),
                strict=True,
            )
        ]

    def _answers(self, source: str) -> list[str]:
        """Read exactly one JSON answer for every expected numeric candidate key."""
        document = TypeAdapter(dict[str, JsonValue]).validate_json(source)
        answers = TypeAdapter(dict[str, JsonValue]).validate_python(document.get("answers"))
        keys = [str(index) for index in range(len(self.candidates))]
        if set(answers) != set(keys):
            raise ValueError("The model returned different batch candidate keys")
        return [json.dumps(answers[key], sort_keys=True) for key in keys]

    def _prompt(
        self,
        guidance: str,
        *,
        rubric_name: str,
        rubric: Mapping[str, str],
    ) -> str:
        """Render keyed candidates that share one rubric but never evidence."""
        payload = {
            str(index): {
                "subject": protocol.candidate.prompt_subject,
                "evidence": list(protocol.evidence.values()),
            }
            for index, protocol in enumerate(self.protocols)
        }
        return (
            f"{guidance}\n\n"
            "Judge every numbered candidate independently. Return one answer under the matching "
            "numeric key in `answers`. Never carry evidence between candidates.\n\n"
            f"Rule instructions\n{self.instructions.strip()}\n\n"
            f"{rubric_name}\n{json.dumps(rubric, sort_keys=True)}\n\n"
            f"Candidates\n{json.dumps(payload, sort_keys=True)}"
        )

    def _schema(self, answer: dict[str, JsonValue]) -> dict[str, JsonValue]:
        """Close one keyed answer object over the exact batch cardinality."""
        keys = [str(index) for index in range(len(self.candidates))]
        required: list[JsonValue] = [*keys]
        answers: dict[str, JsonValue] = {
            "type": "object",
            "properties": {key: answer for key in keys},
            "required": required,
            "additionalProperties": False,
        }
        return {
            "type": "object",
            "properties": {"answers": answers},
            "required": ["answers"],
            "additionalProperties": False,
        }
