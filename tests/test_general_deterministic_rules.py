from typing import TYPE_CHECKING, Literal

import pytest

from mcmr.facts import (
    AuthorshipAssessment,
    AuthorshipSegment,
    AuthorshipSignalFact,
    CallFact,
    CallSite,
    ConfigurationAssignment,
    DependencyFact,
    DependencyRecord,
    DeploymentFact,
    Expression,
    Fact,
    FeatureFlag,
    FeatureFlagFact,
    LengthDistribution,
    LiteralGroupFact,
    MethodCloneGroup,
    MethodGroupFact,
    NodeRef,
    ProjectConfigurationFact,
    ProseSection,
    ProseSegmentFact,
    QuarantinedTest,
    SourceSpan,
    StringExpression,
    StringExpressionFact,
    StringLiteralGroup,
    Waiver,
    WaiverFact,
)
from mcmr.facts import TestSuiteFact as SuiteFact
from mcmr.models import Replace
from mcmr.rules.general.deterministic.configuration.r0001 import hardcoded_path_policy_count
from mcmr.rules.general.deterministic.dependencies.r0005 import dependency_technical_lag
from mcmr.rules.general.deterministic.dependencies.r0007 import explicit_dependency_state_count
from mcmr.rules.general.deterministic.dependencies.r0010 import (
    repeated_external_unary_transformation,
)
from mcmr.rules.general.deterministic.dependencies.r0011 import (
    dependency_evidence_gap_percentage,
)
from mcmr.rules.general.deterministic.deployment.r0001 import deployment_reproducibility
from mcmr.rules.general.deterministic.duplication.r0001 import repeated_class_method_count
from mcmr.rules.general.deterministic.duplication.r0002 import repeated_semantic_string_literal
from mcmr.rules.general.deterministic.lifecycle.r0002 import feature_flag_debt
from mcmr.rules.general.deterministic.strings.r0001 import (
    fragmented_multiline_literal,
    use_multiline_literal,
)
from mcmr.rules.general.deterministic.strings.r0003 import (
    decorative_repeated_separator_count,
)
from mcmr.rules.general.deterministic.testing.r0008 import flaky_test_quarantine_debt
from mcmr.rules.general.deterministic.waivers.r0001 import waiver_debt
from mcmr.rules.general.deterministic.writing.r0001 import ai_associated_pattern_count
from mcmr.rules.general.deterministic.writing.r0002 import ai_associated_segment_coverage
from mcmr.rules.general.deterministic.writing.r0003 import sentence_length_uniformity
from mcmr.rules.general.deterministic.writing.r0004 import paragraph_length_uniformity
from mcmr.rules.general.deterministic.writing.r0005 import sentence_opener_concentration
from mcmr.rules.general.deterministic.writing.r0006 import authorship_detector_signal

if TYPE_CHECKING:
    from tests.conftest import Declared

SPAN = SourceSpan(path="project")


def fact[FactT: Fact](family: type[FactT], **records: Declared) -> FactT:
    """Return one fact of the given family, keyed and located the way every rule here reads it."""
    return family.model_validate({"key": family.__name__, "span": SPAN} | records)


def assignment(
    name: str, kind: Literal["list", "tuple", "set", "other"], *values: str, typed: bool = False
) -> ConfigurationAssignment:
    """Return one configuration assignment listing the given values under a collection kind."""
    return ConfigurationAssignment(
        name=name, collection_kind=kind, values=list(values), is_typed_configuration_field=typed
    )


def test_hardcoded_path_policy_cases() -> None:
    subject = fact(
        ProjectConfigurationFact,
        assignments=[
            assignment("excluded_directories", "list", ".git", ".venv", "build"),
            assignment("ignored", "list", "alpha", "beta", "gamma"),
            assignment("ignored_suffixes", "tuple", ".pyc", ".so", "*.egg-info", typed=True),
        ],
    )
    assert hardcoded_path_policy_count(subject) == 1
    assert hardcoded_path_policy_count(subject, minimum_paths=4) == 0

    # A suffix list qualifies only when every entry reads as a suffix, which is the branch a
    # coverage exclusion for `...` had been swallowing along with the rest of this body.
    suffixes = fact(
        ProjectConfigurationFact,
        assignments=[assignment("ignored_suffixes", "tuple", ".pyc", ".so", "*.egg-info")],
    )
    mixed = fact(
        ProjectConfigurationFact,
        assignments=[assignment("ignored_suffixes", "tuple", ".pyc", "build", ".so")],
    )

    assert hardcoded_path_policy_count(suffixes) == 1
    assert hardcoded_path_policy_count(mixed) == 0


def test_dependency_cases() -> None:
    """Read the manifest for its lag, its states, and its evidence, and the calls for repeats."""
    manifest = fact(
        DependencyFact,
        dependencies=[
            DependencyRecord(
                name="current",
                resolved_release_day=100,
                latest_compatible_release_day=120,
                latest_compatible_version="2.0",
            ),
            DependencyRecord(
                name="lagging",
                resolved_release_day=100,
                latest_compatible_release_day=400,
                latest_compatible_version="3.0",
                project_state="deprecated",
            ),
            DependencyRecord(name="unknown", is_repository_archived=True),
            DependencyRecord(
                name="development",
                resolved_release_day=1,
                latest_compatible_release_day=500,
                latest_compatible_version="1.0",
                is_development=True,
                is_resolved_release_yanked=True,
            ),
        ],
    )
    assert dependency_technical_lag(manifest) == 50.0
    assert dependency_technical_lag(manifest, include_development=True) == pytest.approx(200 / 3)
    assert explicit_dependency_state_count(manifest) == 3
    assert explicit_dependency_state_count(manifest, include_yanked=False) == 2
    assert dependency_evidence_gap_percentage(manifest) == 25.0
    assert (
        dependency_evidence_gap_percentage(manifest.model_copy(update={"dependencies": []})) == 0
    )

    transformations = fact(
        CallFact,
        calls=[
            CallSite(
                qualified_name="inflection.underscore",
                path=path,
                arguments=[Expression(text="value")],
                is_external=True,
            )
            for path in ["src/a.py", "src/b.py", "src/b.py"]
        ]
        + [
            CallSite(
                qualified_name="pathlib.Path",
                path="src/a.py",
                arguments=[Expression(text="value")],
                is_external=True,
                is_standard_library=True,
            )
        ],
    )
    assert repeated_external_unary_transformation(transformations) == 1
    assert repeated_external_unary_transformation(transformations, minimum_files=3) == 0
    assert (
        repeated_external_unary_transformation(
            transformations,
            ignored_callables=("inflection.underscore",),
        )
        == 0
    )


def test_deployment_reproducibility_cases() -> None:
    required = [
        "locked_inputs",
        "build_command",
        "environment",
        "artifact_identity",
        "provenance",
        "migrations",
        "configuration",
        "secrets_boundary",
        "rollback",
    ]
    complete = fact(DeploymentFact, reproducibility_checks=dict.fromkeys(required, True))
    assert deployment_reproducibility(complete) == "reproducible"
    assert (
        deployment_reproducibility(
            complete.model_copy(update={"reproducibility_checks": {"locked_inputs": True}})
        )
        == "partial"
    )
    assert (
        deployment_reproducibility(complete.model_copy(update={"reproducibility_checks": {}}))
        == "nonreproducible"
    )
    assert (
        deployment_reproducibility(complete.model_copy(update={"is_applicable": False}))
        == "not_applicable"
    )


def test_duplication_cases() -> None:
    methods = fact(
        MethodGroupFact,
        groups=[
            MethodCloneGroup(
                normalized_definition="def key(self): return self.name",
                locations=["a.py:1", "b.py:1", "c.py:1"],
                direct_base="Base",
            ),
            MethodCloneGroup(
                normalized_definition="def local(self): return 1",
                locations=["a.py:2", "b.py:2"],
                direct_base="",
            ),
        ],
    )
    assert repeated_class_method_count(methods) == 2

    strings = fact(
        LiteralGroupFact,
        string_groups=[
            StringLiteralGroup(
                value="transient-failure",
                role="retry.reason",
                occurrence_count=3,
                files=["a.py", "b.py"],
            ),
            StringLiteralGroup(
                value="short",
                role="status",
                occurrence_count=5,
                files=["a.py", "b.py"],
            ),
        ],
    )
    assert repeated_semantic_string_literal(strings) == 1


def test_parked_exception_debt_cases() -> None:
    """Three lanes count one shape, an exception parked past the justification that opened it.

    A young flag, a quarantined test under repair, and a waiver stating its reason are accepted,
    while age alone, a recurrence, an expiry already past, a missing reason, and an unknown age
    are what turn each of them back into debt.
    """
    flags = fact(
        FeatureFlagFact,
        flags=[
            FeatureFlag(name="new", age_days=10),
            FeatureFlag(name="stale", age_days=100),
            FeatureFlag(
                name="permission",
                age_days=100,
                role="permission",
                owner="security",
                has_tested_states=True,
            ),
            FeatureFlag(name="expired", age_days=1, is_past_decision_date=True),
        ],
    )
    assert feature_flag_debt(flags) == 2

    quarantined = fact(
        SuiteFact,
        quarantined_tests=[
            QuarantinedTest(
                name="stable repair",
                age_days=3,
                owner="team",
                has_remediation_evidence=True,
            ),
            QuarantinedTest(name="old", age_days=15),
            QuarantinedTest(
                name="recurring",
                age_days=2,
                owner="team",
                has_remediation_evidence=True,
                recurred_after_repair=True,
            ),
        ],
    )
    assert flaky_test_quarantine_debt(quarantined) == 2

    waivers = fact(
        WaiverFact,
        waivers=[
            Waiver(location="src/a.py", age_days=2, metadata={"reason": "stub gap"}),
            Waiver(location="src/b.py", age_days=None, metadata={"reason": "unknown age"}),
            Waiver(location="src/c.py", age_days=2, metadata={}),
            Waiver(
                location="src/d.py",
                age_days=2,
                expires_in_days=-1,
                metadata={"reason": "temporary"},
            ),
            Waiver(location="build/generated.py", metadata={}),
        ],
    )
    assert waiver_debt(waivers) == 3


def test_string_expression_cases() -> None:
    subject = fact(
        StringExpressionFact,
        expressions=[
            StringExpression(
                runtime_value="first\nsecond",
                literal_fragment_count=2,
                node=NodeRef(id="literal", span=SPAN, text='"first\\n" "second"'),
            ),
            StringExpression(
                runtime_value="one wrapped line",
                literal_fragment_count=3,
                wraps_single_runtime_line=True,
            ),
            StringExpression(runtime_value="---", repeated_literal="-", repetition_count=30),
            StringExpression(runtime_value="aaa", repeated_literal="a", repetition_count=30),
        ],
    )
    assert fragmented_multiline_literal(subject) == 1
    assert decorative_repeated_separator_count(subject) == 1

    python = subject.model_copy(update={"language": "python"})
    plan = use_multiline_literal(python)
    assert plan is not None
    assert [rewrite.source for rewrite in plan.rewrites if isinstance(rewrite, Replace)] == [
        '"""first\nsecond"""'
    ]
    assert use_multiline_literal(subject) is None


def test_authorship_signal_cases() -> None:
    """The prose signal arrives as patterns a provider found and as one whole-document verdict.

    Only an eligible segment counts and only for the providers asked about, and a verdict under
    the word floor of the provider that stated it or missing altogether is ineligible.
    """
    segments = fact(
        AuthorshipSignalFact,
        segments=[
            AuthorshipSegment(
                identifier="intro",
                patterns_by_provider={"pangram": ["At its core", "delve"]},
            ),
            AuthorshipSegment(identifier="body", patterns_by_provider={"vale": []}),
            AuthorshipSegment(
                identifier="code",
                patterns_by_provider={"pangram": ["robust"]},
                is_eligible=False,
            ),
        ],
    )
    assert ai_associated_pattern_count(segments) == 2
    assert ai_associated_pattern_count(segments, providers=("vale",)) == 0
    assert ai_associated_segment_coverage(segments) == 50.0

    assessed = fact(
        AuthorshipSignalFact,
        assessment=AuthorshipAssessment(
            provider="pangram",
            signal="ai_like",
            observed_word_count=300,
            minimum_word_count=100,
        ),
    )
    assert authorship_detector_signal(assessed) == "ai_like"
    assert authorship_detector_signal(assessed, minimum_words=400) == "ineligible"
    assert (
        authorship_detector_signal(assessed.model_copy(update={"assessment": None}))
        == "ineligible"
    )


def test_prose_distribution_cases() -> None:
    empty = LengthDistribution(root=[])
    assert LengthDistribution.from_value(empty) is empty
    assert empty.uniformity() == 0.0
    uniform = ProseSection(
        sentence_word_counts=[10, 10, 10, 10, 10],
        paragraph_word_counts=[40, 40, 40, 40],
        sentence_openers=["This", "This", "That", "Other", "This", "Another"],
    )
    varied = ProseSection(
        sentence_word_counts=[3, 5, 10, 20, 40],
        paragraph_word_counts=[30, 45, 80, 120],
        sentence_openers=["A", "I", "Each", "Different", "Word", "Starts"],
    )
    subject = fact(ProseSegmentFact, sections=[uniform, varied])
    assert sentence_length_uniformity(subject) == 100.0
    assert paragraph_length_uniformity(subject) == 100.0
    assert sentence_opener_concentration(subject).value == 50.0
    assert sentence_opener_concentration(subject.model_copy(update={"sections": []})).value == 0.0
