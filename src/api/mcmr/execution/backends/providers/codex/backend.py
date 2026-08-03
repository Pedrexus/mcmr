from enum import StrEnum
from functools import cached_property
from typing import TYPE_CHECKING, ClassVar

from pydantic import Field, InstanceOf

from .....domain import primitives
from ....contracts import (
    Assessment,
    Classification,
    CommandRunner,
    ModelCandidate,
    SubprocessRunner,
)
from ....queries.runtime import ClassificationBackend
from .harness import CodexHarness
from .protocol import CodexProtocol

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .....domain.contracts import Criterion


class CodexBackend(ClassificationBackend):
    """Run each contextual rule through an isolated schema-constrained Codex process."""

    name: ClassVar[str] = "codex"
    binary: primitives.NonEmptyStr = "codex"
    model: primitives.NonEmptyStr = "gpt-5.6-sol"
    reasoning_effort: primitives.NonEmptyStr = "low"
    timeout_seconds: int = Field(default=180, ge=1)
    runner: InstanceOf[CommandRunner] = Field(
        default_factory=SubprocessRunner,
        exclude=True,
        repr=False,
    )

    @cached_property
    def harness(self) -> CodexHarness:
        """Build the configured isolated process harness once."""
        return CodexHarness.model_validate(self, from_attributes=True)

    async def assess_candidate(
        self,
        candidate: ModelCandidate,
        *,
        criteria: Sequence[Criterion],
        instructions: str,
    ) -> Assessment:
        """Assess all predicates for one normalized candidate in one Codex turn."""
        protocol = CodexProtocol(candidate=candidate, instructions=instructions)
        validated = protocol.criteria(criteria)
        source, result = await self.harness.invoke(
            protocol.assessment_schema(validated),
            prompt=protocol.assessment_prompt(validated),
            name="assessment",
        )
        return protocol.assessment(source, validated, self.harness.provenance(result))

    async def classify_candidate[Category: StrEnum](
        self,
        candidate: ModelCandidate,
        *,
        category: type[Category],
        instructions: str,
    ) -> Classification[Category]:
        """Classify one normalized table candidate without reconstructing a fact model."""
        protocol = CodexProtocol(candidate=candidate, instructions=instructions)
        source, result = await self.harness.invoke(
            protocol.classification_schema(category),
            prompt=protocol.classification_prompt(category),
            name="classification",
        )
        return protocol.classification(source, category, self.harness.provenance(result))


CodexBackend.model_rebuild(_types_namespace={"primitives": primitives})
