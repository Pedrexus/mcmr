from time import perf_counter
from typing import TYPE_CHECKING

import anyio
import polars as pl
from patos import FrozenModel, Runtime
from pydantic import PositiveInt

from .....domain.contracts import ModelProvenance, RuleContract, RuleLane, fact_type
from .....execution import ClassificationBackend
from .....execution.queries import ModelQuery
from .....query import frame_value
from .....table import GenericRelation, Table
from ..report import ContextualSweepReport
from ..result import ContextualSweepResult

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Mapping, MutableMapping, Sequence

    from .....domain.contracts import RuleSetting
    from .....facts.foundation import Fact
    from .....rulebook.catalog import Catalog


class ContextualSweep(FrozenModel):
    """Exercise every model rule through one bounded classification backend."""

    backend: Runtime[ClassificationBackend]
    workers: PositiveInt = 8

    @staticmethod
    async def execute_rules(
        rules: Sequence[RuleContract],
        execute: Callable[[int, RuleContract], Coroutine[None, None, None]],
    ) -> None:
        """Start every contextual rule inside one bounded task group."""
        async with anyio.create_task_group() as group:
            for index, rule in enumerate(rules):
                group.start_soon(execute, index, rule)

    @staticmethod
    def first_failure(failure: BaseException) -> BaseException:
        """Return the first concrete failure from nested task-group groups."""
        while isinstance(failure, BaseExceptionGroup):
            failure = failure.exceptions[0]
        return failure

    @staticmethod
    def table(family: type[Fact], rule_id: str) -> Table[Fact]:
        """Build one native-shaped synthetic candidate without constructing a fact model."""
        path = f"contextual/{rule_id}.json"
        frames = {
            GenericRelation.FACTS: pl.DataFrame(
                {
                    "fact_order": pl.Series([0], dtype=pl.UInt64),
                    "fact_id": [f"sweep:{rule_id}"],
                    "path": [path],
                    "start_line": pl.Series([1], dtype=pl.UInt64),
                    "start_column": pl.Series([0], dtype=pl.UInt64),
                    "end_line": pl.Series([1], dtype=pl.UInt64),
                    "end_column": pl.Series([0], dtype=pl.UInt64),
                    "language": ["general"],
                    "sweep": [True],
                }
            ),
            GenericRelation.RECORDS: pl.DataFrame(
                schema={
                    "fact_order": pl.UInt64,
                    "fact_id": pl.String,
                    "relation": pl.String,
                    "parent_id": pl.String,
                    "record_id": pl.String,
                    "ordinal": pl.UInt64,
                    "signal": pl.String,
                    "detail": pl.String,
                    "source": pl.String,
                    "confidence": pl.Float64,
                }
            ),
            GenericRelation.VALUES: pl.DataFrame(
                schema={
                    "fact_order": pl.UInt64,
                    "fact_id": pl.String,
                    "relation": pl.String,
                    "parent_id": pl.String,
                    "ordinal": pl.UInt64,
                    "string_value": pl.String,
                }
            ),
        }
        return Table(family=family, relation_type=GenericRelation, frames=frames)

    async def run(
        self,
        catalog: Catalog,
        settings: Mapping[str, Mapping[str, RuleSetting]],
    ) -> ContextualSweepReport:
        """Run one sparse but valid evidence turn for every contextual rule."""
        definitions = {
            definition.callable: definition
            for definition in catalog.definitions
            if definition.lane != RuleLane.DETERMINISTIC
        }
        rules = [rule for rule in catalog.rules if rule.callable_path in definitions]
        results: dict[int, ContextualSweepResult] = {}
        limiter = anyio.CapacityLimiter(self.workers)
        started = perf_counter()

        async def execute(index: int, rule: RuleContract) -> None:
            definition = definitions[rule.callable_path]
            family = fact_type(rule.hints[next(iter(rule.signature.parameters))])
            subject = self.table(family, definition.id)
            async with limiter:
                query = rule.invoke_table(
                    subject,
                    settings=dict(settings.get(rule.callable_path, {})),
                    dependencies={ClassificationBackend: self.backend},
                )
                if not isinstance(query, ModelQuery):
                    raise TypeError(f"{definition.id} did not return a model query")
                try:
                    resolved = await self.backend.resolve(query)
                except (OSError, RuntimeError, TimeoutError, ValueError) as failure:
                    return self._record_failure(results, index, definition.id, failure)
            values = resolved.values.collect()
            findings = (
                pl.DataFrame()
                if resolved.findings is None
                else resolved.findings.normalized().rows.collect()
            )
            if findings.is_empty():
                raise ValueError(f"{definition.id} returned no model provenance")
            provenance = ModelProvenance(
                backend=frame_value(findings, 0, "provenance_backend", str),
                model=frame_value(findings, 0, "provenance_model", str),
                reasoning_effort=frame_value(findings, 0, "provenance_reasoning_effort", str),
                input_tokens=frame_value(findings, 0, "provenance_input_tokens", int),
                cached_input_tokens=frame_value(
                    findings, 0, "provenance_cached_input_tokens", int
                ),
                output_tokens=frame_value(findings, 0, "provenance_output_tokens", int),
                reasoning_tokens=frame_value(findings, 0, "provenance_reasoning_tokens", int),
            )
            results[index] = ContextualSweepResult(
                rule=definition.id,
                value=frame_value(values, 0, "category_value", str),
                finding_count=findings.height,
                provenance=provenance,
                messages=findings.get_column("message").to_list(),
                evidence_ids=list(
                    dict.fromkeys(
                        identifier
                        for identifiers in findings.get_column("evidence").to_list()
                        for identifier in identifiers
                    )
                ),
            )

        try:
            await self.execute_rules(rules, execute)
        except BaseExceptionGroup as failures:
            raise self.first_failure(failures) from None
        return ContextualSweepReport(
            results=[results[index] for index in range(len(rules))],
            elapsed_seconds=perf_counter() - started,
        )

    def _record_failure(
        self,
        results: MutableMapping[int, ContextualSweepResult],
        index: int,
        rule_id: str,
        failure: OSError | RuntimeError | TimeoutError | ValueError,
    ) -> None:
        """Retain one bounded contextual failure at its stable result position."""
        error = f"{type(failure).__name__}: {failure}"
        results[index] = ContextualSweepResult(
            rule=rule_id,
            value="error",
            finding_count=0,
            provenance=self.backend.unreported_provenance(),
            messages=[error],
            error=error,
        )
