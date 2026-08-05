import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
import pytest
from pydantic import ValidationError

from mcmr import ContextBackend, ContextualConfiguration
from mcmr.contextual.corpus import (
    ContextualCase,
    ContextualCorpus,
    ContextualExpectation,
)
from mcmr.contextual.evaluation import (
    BackendProfile,
    ContextualExperiment,
    ContextualSweep,
)
from mcmr.domain.contracts import (
    RuleContract,
    RuleDependency,
    RuleSetting,
)
from mcmr.execution import (
    ClassificationBackend,
    CodexBackend,
    CriterionValue,
    Gliner2Backend,
)
from mcmr.execution.backends import (
    BatchedBackend,
    SubprocessRunner,
)
from mcmr.facts import Evidence
from mcmr.plugins import Fact, Table
from mcmr.query import RuleQuery
from mcmr.rulebook.catalog import Catalog
from mcmr.rulebook.discovery import RuleModuleDiscovery
from mcmr.table import GenericRelation

from ..backend_values import (
    candidate,
    contextual_case,
    criteria,
)
from ..fakes import (
    Category,
    EmptyAssessmentBackend,
    EmptyBatchBackend,
    FailingBatchBackend,
    FirstCategoryBackend,
    GlinerProbe,
    LabeledBackend,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mcmr.execution.queries import ModelQuery


@pytest.mark.anyio
async def test_the_subprocess_runner_captures_bytes_exit_status_and_timeout() -> None:
    """The real runner is shell-free, byte-safe, and bounded."""
    runner = SubprocessRunner()
    success = await runner(
        [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'out\\xff')"],
        "",
        Path(),
        5,
    )
    failure = await runner(
        [sys.executable, "-c", "import sys; sys.stderr.write('bad'); sys.exit(3)"],
        "",
        Path(),
        5,
    )

    assert success.returncode == 0
    assert success.stdout == "out�"
    assert failure.returncode == 3
    assert failure.stderr == "bad"
    with pytest.raises(TimeoutError):
        await runner(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            "",
            Path(),
            0,
        )


@pytest.mark.anyio
async def test_process_group_kill_tolerates_a_process_that_just_finished() -> None:
    """The timeout race is harmless whether the process is still alive or already gone."""
    alive = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import time; time.sleep(30)",
        start_new_session=True,
    )
    await SubprocessRunner.terminate(alive)

    finished = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "pass",
        start_new_session=True,
    )
    await finished.wait()
    await SubprocessRunner.terminate(finished)


@pytest.mark.anyio
async def test_the_abstract_backend_refuses_direct_classification() -> None:
    with pytest.raises(NotImplementedError):
        await ClassificationBackend.classify_candidate(
            FirstCategoryBackend(),
            candidate(),
            category=Category,
            instructions="Classify the retained facts.",
        )


@pytest.mark.anyio
async def test_the_batched_spine_defers_every_turn_to_its_concrete_backend() -> None:
    """The shared batching spine never invents a transport of its own."""
    with pytest.raises(NotImplementedError):
        await BatchedBackend.turn(
            CodexBackend(),
            {},
            prompt="Judge the retained facts.",
            name="classification",
        )


@pytest.mark.anyio
async def test_gliner_batches_classifications_and_uses_uncertainty_below_threshold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = GlinerProbe(
        [
            {"classification": {"label": "supported", "confidence": 0.9}},
            {"classification": {"label": "supported", "confidence": 0.2}},
        ]
    )
    monkeypatch.setattr(Gliner2Backend, "classifier", property(lambda self: probe))
    backend = Gliner2Backend(model_path=tmp_path, batch_size=4, minimum_confidence=0.6)
    cases = [candidate(), candidate(Evidence(signal="second", detail="two", source="test"))]

    answers = await backend.classify_many(
        cases,
        category=Category,
        instructions="Judge cohesion.",
    )

    assert (
        [answer.value for answer in answers],
        answers[0].evidence,
        answers[0].provenance.backend,
    ) == ([Category.SUPPORTED, Category.UNCERTAIN], ["fact:design:shop/service.py"], "gliner2")
    assert "Judge cohesion" in probe.calls[0][0][0]
    assert probe.calls[0][1:] == (
        "classification",
        '{"supported": "supported", "uncertain": "uncertain"}',
        4,
    )
    assert await backend.classify_many([], category=Category, instructions="Judge.") == []


@pytest.mark.anyio
async def test_gliner_assesses_each_criterion_and_keeps_the_scalar_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = GlinerProbe([{"classification": {"label": "yes", "confidence": 0.8}}])
    monkeypatch.setattr(Gliner2Backend, "classifier", property(lambda self: probe))
    backend = Gliner2Backend(model_path=tmp_path)

    assessed = await backend.assess_many(
        [candidate()],
        criteria=criteria(),
        instructions="Assess structure.",
    )
    classified = await backend.classify_candidate(
        candidate(),
        category=CriterionValue,
        instructions="Classify support.",
    )

    assert [answer.value for answer in assessed[0].answers] == [
        CriterionValue.YES,
        CriterionValue.YES,
    ]
    assert classified.value is CriterionValue.YES
    assert len(probe.calls) == 3


@pytest.mark.anyio
async def test_gliner_requires_explicit_weights_and_exact_batch_cardinality(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="model_path"):
        _ = Gliner2Backend().classifier

    monkeypatch.setattr(
        "mcmr.execution.backends.providers.gliner.GlinerClassifier", lambda path: path
    )
    assert Gliner2Backend(model_path=tmp_path).classifier == tmp_path

    probe = GlinerProbe([])
    monkeypatch.setattr(Gliner2Backend, "classifier", property(lambda self: probe))
    with pytest.raises(ValueError, match="different number"):
        await Gliner2Backend(model_path=tmp_path).classify_many(
            [candidate()],
            category=Category,
            instructions="Judge.",
        )


def test_contextual_corpus_is_versioned_unique_and_explicit(tmp_path: Path) -> None:
    def invalid(expectation: ContextualExpectation | None, message: str) -> None:
        with pytest.raises(ValidationError, match=message):
            if expectation is None:
                ContextualExpectation()
            else:
                ContextualCorpus(cases=[case, case.model_copy(update={"expected": expectation})])

    case = contextual_case(
        "ALL-ARCH1001",
        ContextualExpectation(classification="cohesive"),
    )
    corpus = ContextualCorpus(cases=[case])
    path = tmp_path / "labels.json"
    path.write_text(corpus.model_dump_json(), encoding="utf-8")

    assert (
        ContextualCorpus.read(path),
        corpus.grouped(),
        case.candidate.fact_id,
        case.expected.rendered(),
    ) == (corpus, {"ALL-ARCH1001": [case]}, "case:ALL-ARCH1001", "cohesive")
    invalid(None, "exactly one")
    with pytest.raises(ValidationError, match="exactly one"):
        ContextualExpectation(
            classification="cohesive",
            criteria={"supported": CriterionValue.YES},
        )
    invalid(case.expected, "unique")


def test_backend_profiles_are_smallest_first_and_sol_is_explicitly_optional() -> None:
    routine = BackendProfile.routine()
    extended = BackendProfile.routine(include_sol=True)

    assert [profile.name for profile in routine] == [
        "gliner2-base",
        "luna-none",
        "luna-low",
        "luna-medium",
        "luna-high",
        "terra-medium",
    ]
    assert [profile.name for profile in extended][-1] == "sol-medium"
    assert isinstance(routine[0].build(ContextualConfiguration(), 2), Gliner2Backend)
    assert isinstance(routine[1].build(ContextualConfiguration(), 2), CodexBackend)


@pytest.mark.anyio
async def test_labeled_experiment_recommends_the_first_exact_profile_per_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = Catalog(modules=RuleModuleDiscovery().modules)
    experiment = ContextualExperiment(
        profiles=[
            BackendProfile(
                name="small",
                backend=ContextBackend.CODEX,
                model="small",
                reasoning_effort="low",
            ),
            BackendProfile(
                name="large",
                backend=ContextBackend.CODEX,
                model="large",
                reasoning_effort="medium",
            ),
        ]
    )
    by_id = {
        definition.id: next(
            rule for rule in catalog.rules if rule.callable_path == definition.callable
        )
        for definition in catalog.definitions
    }
    retry = experiment.template(by_id["ALL-RELI1003"], {})
    corpus = ContextualCorpus(
        cases=[
            contextual_case(
                "ALL-ARCH1001",
                ContextualExpectation(classification="cohesive"),
            ),
            contextual_case(
                "ALL-RELI1003",
                ContextualExpectation(
                    criteria={criterion.name: CriterionValue.YES for criterion in retry.criteria}
                ),
            ),
        ]
    )

    def build(
        profile: BackendProfile,
        configuration: ContextualConfiguration,
        workers: int,
    ) -> ClassificationBackend:
        assert configuration and workers == 8
        return LabeledBackend(
            classification_value="mixed" if profile.name == "small" else "cohesive"
        )

    monkeypatch.setattr(BackendProfile, "build", build)
    report = await experiment.run(
        catalog,
        corpus,
        ContextualConfiguration(),
        {},
        require_complete=False,
    )

    assert (
        [result.accuracy for result in report.profiles],
        [result.model_calls for result in report.profiles],
        [result.input_tokens for result in report.profiles],
        [result.cached_input_tokens for result in report.profiles],
        [result.output_tokens for result in report.profiles],
        [result.reasoning_tokens for result in report.profiles],
        all(result.reasoning_characters > 0 for result in report.profiles),
        report.recommendations,
        report.unresolved,
        corpus.cases[1].expected.rendered(),
    ) == (
        [50.0, 100.0],
        [2, 2],
        [0, 0],
        [0, 0],
        [0, 0],
        [0, 0],
        True,
        {"ALL-ARCH1001": "large", "ALL-RELI1003": "small"},
        [],
        {criterion.name: "yes" for criterion in retry.criteria},
    )


@pytest.mark.anyio
async def test_contextual_experiment_rejects_incomplete_unknown_and_wrong_mode_labels() -> None:
    catalog = Catalog(modules=RuleModuleDiscovery().modules)
    experiment = ContextualExperiment(profiles=BackendProfile.routine()[:1])

    async def rejected(
        case: ContextualCase, message: str, *, require_complete: bool = False
    ) -> None:
        """Require one invalid corpus label to fail before backend work."""
        with pytest.raises(ValueError, match=message):
            await experiment.run(
                catalog,
                ContextualCorpus(cases=[case]),
                ContextualConfiguration(),
                {},
                require_complete=require_complete,
            )

    await rejected(
        contextual_case(
            "ALL-ARCH1001",
            ContextualExpectation(classification="cohesive"),
        ),
        "is missing",
        require_complete=True,
    )
    await rejected(
        contextual_case(
            "ALL-MODU0001",
            ContextualExpectation(classification="cohesive"),
        ),
        "Unknown contextual",
    )
    await rejected(
        contextual_case(
            "ALL-ARCH1001",
            ContextualExpectation(criteria={"supported": CriterionValue.YES}),
        ),
        "classification label",
    )
    rule = next(
        rule
        for rule in catalog.rules
        if rule.callable_path.endswith("reliability.r1003.bounded_work")
    )
    assert experiment.template(rule, {}).criteria
    await rejected(
        contextual_case(
            "ALL-RELI1003",
            ContextualExpectation(criteria={"wrong predicate": CriterionValue.YES}),
        ),
        "criteria differ",
    )


@pytest.mark.anyio
async def test_contextual_experiment_retains_backend_errors() -> None:
    async def failure(
        backend: ClassificationBackend,
        template: ModelQuery,
        case: ContextualCase,
    ) -> str:
        """Return the explicit error retained for one controlled backend failure."""
        trials = await experiment.evaluate(experiment.profiles[0], backend, template, [case])
        return trials[0].error

    catalog = Catalog(modules=RuleModuleDiscovery().modules)
    experiment = ContextualExperiment(profiles=BackendProfile.routine()[:1])
    by_id = {
        definition.id: next(
            rule for rule in catalog.rules if rule.callable_path == definition.callable
        )
        for definition in catalog.definitions
    }
    case = contextual_case(
        "ALL-ARCH1001",
        ContextualExpectation(classification="cohesive"),
    )
    template = experiment.template(by_id[case.rule], {})
    retry_template = experiment.template(by_id["ALL-RELI1003"], {})
    retry_case = contextual_case(
        "ALL-RELI1003",
        ContextualExpectation(
            criteria={criterion.name: CriterionValue.YES for criterion in retry_template.criteria}
        ),
    )
    errors = (
        await failure(EmptyBatchBackend(classification_value="cohesive"), template, case),
        await failure(FailingBatchBackend(classification_value="cohesive"), template, case),
        await failure(
            EmptyAssessmentBackend(classification_value="cohesive"), retry_template, retry_case
        ),
        await failure(
            FailingBatchBackend(classification_value="cohesive"), retry_template, retry_case
        ),
    )
    assert (
        "different number of answers" in errors[0],
        "RuntimeError" in errors[1],
        "different number of answers" in errors[2],
        "RuntimeError" in errors[3],
    ) == (True, True, True, True)


def test_contextual_experiment_rejects_a_deterministic_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A contextual experiment refuses a rule from the deterministic lane."""
    catalog = Catalog(modules=RuleModuleDiscovery().modules)
    experiment = ContextualExperiment(profiles=BackendProfile.routine()[:1])
    by_id = {
        definition.id: next(
            rule for rule in catalog.rules if rule.callable_path == definition.callable
        )
        for definition in catalog.definitions
    }

    def deterministic_query(
        self: RuleContract,
        subject: Table[Fact],
        *,
        settings: Mapping[str, RuleSetting],
        dependencies: Mapping[type, RuleDependency],
    ) -> RuleQuery[bool]:
        del self, subject, settings, dependencies
        return RuleQuery.boolean(
            ContextualSweep.table(Fact, "ALL-DEMO1001").lazy(GenericRelation.FACTS),
            pl.lit(False),
        )

    rule = by_id["ALL-ARCH1001"]
    monkeypatch.setattr(type(rule), "invoke_table", deterministic_query)
    with pytest.raises(TypeError, match="did not return a contextual model query"):
        experiment.template(rule, {})
