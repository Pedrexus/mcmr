import json
from enum import StrEnum, auto
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
from anyio import Path as AsyncPath
from pydantic import JsonValue, TypeAdapter

from mcmr.domain.contracts import RuleValue
from mcmr.execution import (
    Assessment,
    Classification,
    ClassificationBackend,
    CriterionAnswer,
    CriterionValue,
    ModelCandidate,
)
from mcmr.query import RuleQuery

from .backend_values import provenance

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mcmr.domain.contracts import Criterion
    from mcmr.execution import CommandResult
    from mcmr.execution.queries import ModelQuery


class Category(StrEnum):
    """Small closed rubric used to verify the isolated harness."""

    SUPPORTED = auto()
    UNCERTAIN = auto()


class CertainCategory(StrEnum):
    """Closed rubric with no uncertainty answer."""

    SUPPORTED = auto()


class FirstCategoryBackend(ClassificationBackend):
    """Return the first closed answer while preserving normal provenance."""

    async def classify_candidate[Category: StrEnum](
        self,
        candidate: ModelCandidate,
        *,
        category: type[Category],
        instructions: str,
    ) -> Classification[Category]:
        assert instructions
        return Classification(
            value=next(iter(category)),
            reasoning="Controlled classification for contract verification.",
            evidence=list(candidate.retained)[:8],
            confidence=1.0,
            provenance=provenance(),
        )


class PartlyFailingBackend(FirstCategoryBackend):
    """Reject only the candidate selected by one batch isolation test."""

    async def classify_candidate[Category: StrEnum](
        self,
        candidate: ModelCandidate,
        *,
        category: type[Category],
        instructions: str,
    ) -> Classification[Category]:
        if candidate.path == "broken.py":
            raise ValueError("model cited unknown evidence")
        return await super().classify_candidate(
            candidate,
            category=category,
            instructions=instructions,
        )


class NoFindingsBackend(FirstCategoryBackend):
    """Resolve a valid category while deliberately omitting model provenance."""

    async def resolve[Category: StrEnum](
        self,
        query: ModelQuery[Category],
    ) -> RuleQuery[RuleValue]:
        resolved: RuleQuery[str] = RuleQuery.category(
            query.candidates,
            pl.lit(str(next(iter(query.category)))),
        )
        return RuleQuery[RuleValue](values=resolved.values)


class LabeledBackend(ClassificationBackend):
    """Return configured labels for contextual experiment tests."""

    classification_value: str

    async def assess_candidate(
        self,
        candidate: ModelCandidate,
        *,
        criteria: Sequence[Criterion],
        instructions: str,
    ) -> Assessment:
        return Assessment(
            answers=[
                CriterionAnswer(
                    criterion=criterion.name,
                    value=CriterionValue.YES,
                    reasoning=instructions,
                    evidence=list(candidate.retained),
                    confidence=1.0,
                    provenance=provenance(),
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
        return Classification(
            value=category(self.classification_value),
            reasoning=instructions,
            evidence=list(candidate.retained),
            confidence=1.0,
            provenance=provenance(),
        )


class EmptyBatchBackend(LabeledBackend):
    """Return the wrong cardinality so the experiment retains one backend failure."""

    async def classify_many[Category: StrEnum](
        self,
        candidates: Sequence[ModelCandidate],
        *,
        category: type[Category],
        instructions: str,
    ) -> list[Classification[Category]]:
        assert candidates and category and instructions
        return []


class EmptyAssessmentBackend(LabeledBackend):
    """Return the wrong assessment cardinality for experiment failure coverage."""

    async def assess_many(
        self,
        candidates: Sequence[ModelCandidate],
        *,
        criteria: Sequence[Criterion],
        instructions: str,
    ) -> list[Assessment]:
        assert candidates and criteria and instructions
        return []


class FailingBatchBackend(LabeledBackend):
    """Raise one bounded backend failure from either native batch lane."""

    async def assess_many(
        self,
        candidates: Sequence[ModelCandidate],
        *,
        criteria: Sequence[Criterion],
        instructions: str,
    ) -> list[Assessment]:
        raise RuntimeError((candidates, criteria, instructions))

    async def classify_many[Category: StrEnum](
        self,
        candidates: Sequence[ModelCandidate],
        *,
        category: type[Category],
        instructions: str,
    ) -> list[Classification[Category]]:
        raise RuntimeError((candidates, category, instructions))


class GlinerProbe:
    """Return controlled native GLiNER JSON and retain the exact batch call."""

    def __init__(self, payload: Sequence[dict[str, JsonValue]]) -> None:
        self.payload = list(payload)
        self.calls: list[tuple[list[str], str, str, int]] = []

    def classify(
        self,
        texts: list[str],
        task: str,
        *,
        labels: str,
        batch_size: int,
    ) -> str:
        """Return the controlled payload in the native binding's JSON shape."""
        self.calls.append((texts, task, labels, batch_size))
        return json.dumps(self.payload)


class StubRunner:
    """Write one controlled Codex payload and retain the invocation for inspection."""

    def __init__(
        self,
        payload: dict[str, JsonValue] | None,
        result: CommandResult,
    ) -> None:
        self.payload = payload
        self.result = result
        self.calls: list[tuple[list[str], str, Path, int]] = []
        self.schema: dict[str, JsonValue] | None = None

    async def __call__(
        self,
        command: list[str],
        prompt: str,
        cwd: Path,
        timeout_seconds: int,
    ) -> CommandResult:
        """Write the controlled answer where the command asked and return its event stream."""
        self.calls.append((command, prompt, cwd, timeout_seconds))
        schema = Path(command[command.index("--output-schema") + 1])
        self.schema = TypeAdapter(dict[str, JsonValue]).validate_json(
            await AsyncPath(schema).read_text()
        )
        if self.payload is not None:
            output = Path(command[command.index("--output-last-message") + 1])
            await AsyncPath(output).write_text(json.dumps(self.payload))
        return self.result
