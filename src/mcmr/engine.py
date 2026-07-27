import inspect
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from enum import StrEnum
from functools import cached_property, partial
from time import perf_counter_ns
from typing import TYPE_CHECKING, Literal, get_args, get_origin

from pydantic import SkipValidation

from .backends import RuleDependency
from .bases import FrozenFlexModel
from .catalog import Catalog
from .concurrency import WorkerPool, available_workers
from .models import (
    Edit,
    EngineReport,
    EngineStats,
    Finding,
    FixContract,
    Observation,
    OutputContract,
    Pending,
    Reported,
    RuleAnswer,
    RuleContract,
    RuleScope,
    RuleSetting,
    RuleValue,
    answered,
    declared,
    explained,
    fact_type,
    output_contract,
    reported_value,
)

if TYPE_CHECKING:
    from .facts import Fact


class MockBackend(FrozenFlexModel):
    """Return type-correct values while performing no analysis work."""

    async def evaluate(self, rule: RuleContract, fact: Fact) -> RuleValue:
        """Return one deterministic placeholder for the declared output type."""
        annotation = declared(rule.hints["return"])
        if isinstance(annotation, type) and issubclass(annotation, Reported):
            annotation = declared(reported_value(annotation))
        if get_origin(annotation) is Literal:
            return str(get_args(annotation)[0])
        if isinstance(annotation, type) and issubclass(annotation, StrEnum):
            return next(iter(annotation))
        if annotation is bool:
            return False
        if annotation is int:
            return 0
        if annotation is float:
            return 0.0
        return ""


class Engine(FrozenFlexModel, ABC):
    """Run one selection of rules over the fact streams a provider built.

    Which stream a rule reads is not something an engine gets to decide. The rule states it by
    typing its first parameter, and both engines here have to read that the same way, because the
    mock engine exists to measure the framework cost of the real one and a floor that planned
    differently would be measuring something nobody runs.
    """

    rules: list[SkipValidation[RuleContract]]
    fixes: list[SkipValidation[FixContract]] = []

    @abstractmethod
    async def run(self, workspace: Mapping[type[Fact], Sequence[Fact]]) -> EngineReport:
        """Execute every selected rule over its facts and report what the run cost."""

    def plan(
        self,
        workspace: Mapping[type[Fact], Sequence[Fact]],
    ) -> dict[type[Fact], list[RuleContract]]:
        """Group executable rules by the exact fact stream requested by typing."""
        plan: dict[type[Fact], list[RuleContract]] = {}
        for rule in self.rules:
            first = next(iter(rule.signature.parameters.values()))
            required = fact_type(rule.hints[first.name])
            if required not in workspace:
                raise KeyError(f"Missing fact stream {required.__name__}")
            plan.setdefault(required, []).append(rule)
        return plan


class MockEngine(Engine):
    """Plan typed facts once and measure framework-only dispatch overhead."""

    backend: MockBackend = MockBackend()

    async def run(self, workspace: Mapping[type[Fact], Sequence[Fact]]) -> EngineReport:
        """Execute every selected mock rule over its exact fact stream."""
        started = perf_counter_ns()
        planning_started = perf_counter_ns()
        plan = self.plan(workspace)
        planning_nanoseconds = perf_counter_ns() - planning_started
        execution_started = perf_counter_ns()
        observations = [
            Observation(
                rule=rule.callable_path,
                fact=fact.key,
                value=await self.backend.evaluate(rule, fact),
                span=fact.span,
            )
            for fact_type, rules in plan.items()
            for fact in workspace[fact_type]
            for rule in rules
        ]
        execution_nanoseconds = perf_counter_ns() - execution_started
        fix_planning_started = perf_counter_ns()
        fixes_by_rule: dict[str, list[FixContract]] = {}
        for fix in self.fixes:
            fixes_by_rule.setdefault(fix.rule_callable, []).append(fix)
        fix_candidate_count = sum(len(fixes_by_rule.get(item.rule, [])) for item in observations)
        fix_planning_nanoseconds = perf_counter_ns() - fix_planning_started
        fact_count = sum(len(workspace[item]) for item in plan)
        return EngineReport(
            observations=observations,
            stats=EngineStats(
                rule_count=len(self.rules),
                fact_count=fact_count,
                invocation_count=len(observations),
                provider_read_count=len(plan),
                fix_count=len(self.fixes),
                fix_candidate_count=fix_candidate_count,
                planning_nanoseconds=planning_nanoseconds,
                execution_nanoseconds=execution_nanoseconds,
                fix_planning_nanoseconds=fix_planning_nanoseconds,
                total_nanoseconds=perf_counter_ns() - started,
            ),
        )


class RuleEngine(Engine):
    """Execute rule callables over provider-built fact streams."""

    settings: Mapping[str, Mapping[str, RuleSetting]] = {}
    dependencies: Mapping[type, SkipValidation[RuleDependency]] = {}
    pool: WorkerPool = WorkerPool(workers=available_workers())

    @cached_property
    def repairs(self) -> dict[str, FixContract]:
        """Return the fix each rule declared as its default, keyed by the rule it repairs.

        Only a declared default is here. A rule offering several repairs has already said that
        choosing between them is not the framework's decision, so a finding from one of those
        carries the choice a rule states rather than whichever fix happened to be discovered first.
        """
        return {fix.rule_callable: fix for fix in self.fixes if fix.is_default}

    async def run(self, workspace: Mapping[type[Fact], Sequence[Fact]]) -> EngineReport:
        """Invoke every selected rule with validated evidence and explicit settings.

        Each fact becomes one batch carrying every rule that reads it. Batches run through the
        bounded worker pool, which is real parallelism on a free-threaded interpreter and one
        deterministic worker anywhere else. An asynchronous rule only builds its coroutine inside
        the batch; the event loop awaits it here, so model and backend work keeps its own
        concurrency instead of occupying a worker thread.
        """
        started = perf_counter_ns()
        planning_started = perf_counter_ns()
        plan = self.plan(workspace)
        contracts = {
            rule.callable_path: output_contract(rule.hints["return"])
            for rules in plan.values()
            for rule in rules
        }
        selections = {
            (required, language): self.selected(rules, language)
            for required, rules in plan.items()
            for language in {fact.language for fact in workspace[required]}
        }
        work = [
            (selections[required, fact.language], fact)
            for required in plan
            for fact in workspace[required]
        ]
        reached = {rule.callable_path for rules in selections.values() for rule in rules}
        batches = [partial(self.evaluate, chunk, contracts) for chunk in self.pool.chunked(work)]
        planning_nanoseconds = perf_counter_ns() - planning_started
        execution_started = perf_counter_ns()
        results = await self.pool.map(batches)
        observations = [
            item if isinstance(item, Observation) else await self.settle(item)
            for batch in results
            for item in batch
        ]
        execution_nanoseconds = perf_counter_ns() - execution_started
        fix_planning_started = perf_counter_ns()
        fixes_by_rule = {
            rule.callable_path: [
                fix for fix in self.fixes if fix.rule_callable == rule.callable_path
            ]
            for rule in self.rules
        }
        fix_candidate_count = sum(len(fixes_by_rule[item.rule]) for item in observations)
        fix_planning_nanoseconds = perf_counter_ns() - fix_planning_started
        fact_count = sum(len(workspace[item]) for item in plan)
        return EngineReport(
            observations=observations,
            stats=EngineStats(
                rule_count=len(self.rules),
                skipped_rule_count=sum(rule.callable_path not in reached for rule in self.rules),
                fact_count=fact_count,
                invocation_count=len(observations),
                provider_read_count=len(plan),
                fix_count=len(self.fixes),
                fix_candidate_count=fix_candidate_count,
                planning_nanoseconds=planning_nanoseconds,
                execution_nanoseconds=execution_nanoseconds,
                fix_planning_nanoseconds=fix_planning_nanoseconds,
                total_nanoseconds=perf_counter_ns() - started,
            ),
        )

    def evaluate(
        self,
        work: Sequence[tuple[Sequence[RuleContract], Fact]],
        contracts: Mapping[str, OutputContract],
    ) -> list[Observation | Pending]:
        """Invoke every rule over its facts and validate what returned, off the event loop.

        A synchronous rule leaves this batch as a finished observation, so validation and result
        construction stay in the worker with the rule that produced them. An asynchronous rule
        returns its unstarted coroutine, which is an ordinary object until somebody awaits it, so
        the batch itself stays a plain synchronous call and the event loop keeps that concurrency.
        """
        return [
            Pending(rule=rule, subject=fact, outcome=outcome, contract=contracts[path])
            if inspect.isawaitable(outcome)
            else self.observed(path, fact, contracts[path], outcome)
            for rules, fact in work
            for rule in rules
            for path in (rule.callable_path,)
            for outcome in (
                rule.invoke(
                    fact,
                    settings=self.settings.get(path, {}),
                    dependencies=self.dependencies,
                ),
            )
        ]

    async def settle(self, pending: Pending) -> Observation:
        """Await one asynchronous rule and build the observation the value it produced makes."""
        return self.observed(
            pending.rule.callable_path,
            pending.subject,
            pending.contract,
            await pending.outcome,
        )

    def observed(
        self, path: str, fact: Fact, contract: OutputContract, answer: RuleAnswer
    ) -> Observation:
        """Return one finished observation from whichever shape a rule answered with.

        A rule that answers with a bare scalar and a rule that answers with the same scalar beside
        its findings both arrive here, which is what lets the catalog migrate one rule at a time
        without the engine holding two paths through it.
        """
        if not isinstance(answer, Reported | bool | int | float | str):
            raise TypeError(f"{path} returned an unsupported value")
        return Observation(
            rule=path,
            fact=fact.key,
            value=self.validated(path, contract, answered(answer)),
            span=fact.span,
            findings=self.repaired(path, fact, explained(answer)),
        )

    def repaired(self, path: str, fact: Fact, findings: Sequence[Finding]) -> tuple[Finding, ...]:
        """Attach the default fix of one rule to the findings that state no repair of their own.

        The fix already knows how to rewrite this fact, so a rule that migrated does not restate
        it. What the fix produces repairs the fact, which is why every finding on that fact that
        proposed nothing receives it, and a finding that named its own repair keeps it.
        """
        fix = self.repairs.get(path)
        if fix is None or all(finding.repair is not None for finding in findings):
            return tuple(findings)
        plan = fix.invoke(fact, self.settings.get(path, {}))
        if plan is None:
            return tuple(findings)
        repair = Edit(plan=plan, safety=fix.safety)
        return tuple(
            finding
            if finding.repair is not None
            else finding.model_copy(update={"repair": repair})
            for finding in findings
        )

    def selected(self, rules: Sequence[RuleContract], language: str | None) -> list[RuleContract]:
        """Return the rules of one stream that can actually run against one language.

        A rule runs when three things hold: its fact stream exists, its language matches or it is
        general, and every dependency it declares was supplied. A rule that fails any of them is
        skipped rather than refused, because a repository holding one language, or a run without a
        model backend, should not have to deselect the rules it cannot use. The report counts those
        skips so a selection that reached nothing stays visible.
        """
        return [
            rule
            for rule in rules
            for scope in (Catalog.identity(rule.module)[0],)
            if (scope is RuleScope.GENERAL or scope == language)
            and all(hint in self.dependencies for _, hint in rule.injected)
        ]

    @staticmethod
    def validated(path: str, contract: OutputContract, value: RuleValue) -> RuleValue:
        """Validate one runtime value against the rule's closed output contract."""
        output, _, categories = contract
        match output:
            case "bool" if type(value) is bool:
                return value
            case "int" if type(value) is int:
                return value
            case "float" if type(value) is float:
                return value
            case "str" if isinstance(value, str):
                return value
            case "category" if isinstance(value, str) and value in categories:
                return value
            case _:
                raise TypeError(f"{path} returned an invalid {output} value")
