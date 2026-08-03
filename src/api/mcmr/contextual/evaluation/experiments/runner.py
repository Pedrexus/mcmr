from time import perf_counter
from typing import TYPE_CHECKING, Annotated

from patos import FrozenModel
from pydantic import Field, PositiveInt

from ....domain.contracts import RuleLane, fact_type
from ....execution import ClassificationBackend
from ....execution.queries import ModelMode, ModelQuery
from ..profiles import BackendProfile, ProfileExperiment
from ..sweeps import ContextualSweep
from .evaluator import CaseEvaluator
from .report import ContextualExperimentReport

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence, Set

    from ....domain.contracts import RuleContract, RuleSetting
    from ....project import ContextualConfiguration
    from ....rulebook.catalog import Catalog
    from ...corpus.case import ContextualCase
    from ...corpus.model import ContextualCorpus
    from ..cases import ContextualTrial


class ContextualExperiment(FrozenModel):
    """Run a frozen labeled corpus through an ordered backend profile matrix."""

    profiles: Annotated[list[BackendProfile], Field(min_length=1)]
    workers: PositiveInt = 8

    @staticmethod
    async def evaluate(
        profile: BackendProfile,
        backend: ClassificationBackend,
        template: ModelQuery,
        cases: Sequence[ContextualCase],
    ) -> list[ContextualTrial]:
        """Batch one rule's cases through a backend and compare exact answers."""
        return await CaseEvaluator(
            profile=profile,
            backend=backend,
            template=template,
            cases=cases,
        ).run()

    @staticmethod
    def template(rule: RuleContract, settings: Mapping[str, RuleSetting]) -> ModelQuery:
        """Ask the actual rule for the exact rubric each backend must satisfy."""
        family = fact_type(rule.hints[next(iter(rule.signature.parameters))])
        query = rule.invoke_table(
            ContextualSweep.table(family, rule.id),
            settings=dict(settings),
            dependencies={ClassificationBackend: ClassificationBackend.find("codex")()},
        )
        if not isinstance(query, ModelQuery):
            raise TypeError(f"{rule.id} did not return a contextual model query")
        return query

    async def run(
        self,
        catalog: Catalog,
        corpus: ContextualCorpus,
        configuration: ContextualConfiguration,
        settings: Mapping[str, Mapping[str, RuleSetting]],
        *,
        require_complete: bool = True,
    ) -> ContextualExperimentReport:
        """Evaluate exact labels and retain errors as failed trials."""
        rules, stated = self._rules(catalog, corpus, require_complete=require_complete)
        templates = self._templates(rules, stated, settings)
        self._validate(corpus, templates)
        results = [
            await self._profile_result(profile, configuration, self.workers, templates, corpus)
            for profile in self.profiles
        ]
        return ContextualExperimentReport(profiles=results)

    @staticmethod
    async def _profile_result(
        profile: BackendProfile,
        configuration: ContextualConfiguration,
        workers: int,
        templates: Mapping[str, ModelQuery],
        corpus: ContextualCorpus,
    ) -> ProfileExperiment:
        """Run all reviewed rules through one backend profile."""
        backend = profile.build(configuration, workers)
        started = perf_counter()
        trials = [
            trial
            for rule_id, cases in corpus.grouped().items()
            for trial in await ContextualExperiment.evaluate(
                profile,
                backend,
                templates[rule_id],
                cases,
            )
        ]
        elapsed = perf_counter() - started
        return ProfileExperiment(profile=profile, trials=trials, elapsed_seconds=elapsed)

    @staticmethod
    def _rules(
        catalog: Catalog,
        corpus: ContextualCorpus,
        *,
        require_complete: bool,
    ) -> tuple[dict[str, RuleContract], set[str]]:
        """Resolve reviewed contextual rules and validate corpus coverage."""
        by_path = {rule.callable_path: rule for rule in catalog.rules}
        rules = {definition.id: by_path[definition.callable] for definition in catalog.definitions}
        contextual = {
            definition.id
            for definition in catalog.definitions
            if definition.lane == RuleLane.CONTEXTUAL
        }
        stated = set(corpus.grouped())
        if unknown := sorted(stated - contextual):
            raise ValueError(f"Unknown contextual rules {', '.join(unknown)}")
        if require_complete and (missing := sorted(contextual - stated)):
            raise ValueError(f"Contextual corpus is missing {', '.join(missing)}")
        return rules, stated

    @staticmethod
    def _templates(
        rules: Mapping[str, RuleContract],
        stated: Set[str],
        settings: Mapping[str, Mapping[str, RuleSetting]],
    ) -> dict[str, ModelQuery]:
        """Build each reviewed rule's real contextual query."""
        return {
            rule_id: ContextualExperiment.template(
                rules[rule_id],
                settings.get(rules[rule_id].callable_path, {}),
            )
            for rule_id in stated
        }

    @staticmethod
    def _validate(corpus: ContextualCorpus, templates: Mapping[str, ModelQuery]) -> None:
        """Require labels to match every rule's answer contract."""
        for case in corpus.cases:
            ContextualExperiment._validate_case(case, templates[case.rule])

    @staticmethod
    def _validate_case(case: ContextualCase, template: ModelQuery) -> None:
        """Require one label to match its rule's answer contract."""
        if template.mode is ModelMode.CLASSIFY:
            if case.expected.classification is None:
                raise ValueError(f"{case.rule} case {case.name} needs a classification label")
            template.category(case.expected.classification)
            return
        expected = set(case.expected.criteria)
        required = {criterion.name for criterion in template.criteria}
        if expected != required:
            raise ValueError(
                f"{case.rule} case {case.name} criteria differ from its rule contract"
            )
