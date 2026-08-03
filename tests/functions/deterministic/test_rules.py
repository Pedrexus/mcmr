from typing import TYPE_CHECKING, Literal

import pytest

from mcmr import Numeric
from mcmr.domain.policy import LengthDistribution
from mcmr.facts import (
    AuthorshipMatch,
    AuthorshipSignalFact,
    CallFact,
    ConfigurationAssignment,
    DependencyFact,
    DependencyProjectState,
    DependencyRecord,
    DependencyReleaseState,
    DependencyRepositoryState,
    DeploymentFact,
    FeatureFlag,
    FeatureFlagFact,
    LiteralGroupFact,
    LiteralStringExpression,
    MethodCloneGroup,
    MethodGroupFact,
    NodeRef,
    ProjectConfigurationFact,
    ProseSection,
    ProseSegmentFact,
    QuarantinedTest,
    RepeatedStringExpression,
    SourceSpan,
    StringExpressionFact,
    StringLiteralGroup,
    Waiver,
    WaiverFact,
)
from mcmr.facts import TestFunctionFact as QuarantineFact
from mcmr.rules.general import (
    ai_associated_pattern_count,
    decorative_repeated_separator_count,
    dependency_evidence_gap_percentage,
    dependency_technical_lag,
    deployment_reproducibility,
    explicit_dependency_state_count,
    feature_flag_debt,
    flaky_test_quarantine_debt,
    fragmented_multiline_literal,
    hardcoded_path_policy_count,
    paragraph_length_uniformity,
    repeated_class_method_count,
    repeated_external_unary_transformation,
    repeated_semantic_string_literal,
    sentence_length_uniformity,
    sentence_opener_concentration,
    waiver_debt,
)
from mcmr.table import AnalysisSession

from .support import answer, fact, native_query

if TYPE_CHECKING:
    from pathlib import Path

_SPAN = SourceSpan(path="project")


def test_hardcoded_path_policy_cases() -> None:
    def assignment(
        name: str,
        kind: Literal["list", "tuple", "set", "other"],
        *values: str,
        typed: bool = False,
    ) -> ConfigurationAssignment:
        """Return one configuration assignment with the selected values."""
        return ConfigurationAssignment(
            name=name,
            collection_kind=kind,
            values=list(values),
            is_typed_configuration_field=typed,
        )

    subject = fact(
        ProjectConfigurationFact,
        assignments=[
            assignment("excluded_directories", "list", ".git", ".venv", "build"),
            assignment("ignored", "list", "alpha", "beta", "gamma"),
            assignment("ignored_suffixes", "tuple", ".pyc", ".so", "*.egg-info", typed=True),
        ],
    )
    assert answer(hardcoded_path_policy_count, subject).value == 1
    assert answer(hardcoded_path_policy_count, subject, minimum_paths=4).value == 0

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

    assert answer(hardcoded_path_policy_count, suffixes).value == 1
    assert answer(hardcoded_path_policy_count, mixed).value == 0


def test_dependency_cases(tmp_path: Path) -> None:
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
                project_state=DependencyProjectState.DEPRECATED,
            ),
            DependencyRecord(
                name="unknown",
                repository_state=DependencyRepositoryState.ARCHIVED,
            ),
            DependencyRecord(
                name="development",
                resolved_release_day=1,
                latest_compatible_release_day=500,
                latest_compatible_version="1.0",
                is_development=True,
                resolved_release_state=DependencyReleaseState.YANKED,
            ),
        ],
    )
    assert (
        answer(dependency_technical_lag, manifest).value,
        answer(dependency_technical_lag, manifest, include_development=True).value,
        answer(explicit_dependency_state_count, manifest).value,
        answer(explicit_dependency_state_count, manifest, include_yanked=False).value,
        answer(dependency_evidence_gap_percentage, manifest).value,
        dependency_evidence_gap_percentage.policy,
        answer(
            dependency_evidence_gap_percentage,
            manifest.model_copy(update={"dependencies": []}),
        ).value,
    ) == (
        50.0,
        pytest.approx(200 / 3),
        3,
        2,
        25.0,
        Numeric(maximum=5),
        0,
    )

    (tmp_path / "a.py").write_text(
        """import inflection
from pathlib import Path

first = inflection.underscore(value)
path = Path(value)
""",
        encoding="utf-8",
    )
    (package := tmp_path / "pkg").mkdir()
    (package / "b.py").write_text(
        """import inflection

second = inflection.underscore(value)
third = inflection.underscore(other)
""",
        encoding="utf-8",
    )
    calls = AnalysisSession(
        tmp_path,
        suffixes=[".py"],
        typed_families=[CallFact.__name__],
    ).call_tables()
    repeated = native_query(repeated_external_unary_transformation, calls)
    assert repeated.findings is not None
    variants = [
        native_query(repeated_external_unary_transformation, calls, minimum_files=3),
        native_query(
            repeated_external_unary_transformation,
            calls,
            ignored_callables=["inflection.underscore"],
        ),
        native_query(
            repeated_external_unary_transformation,
            calls,
            transformation_names=["convert"],
        ),
    ]
    assert (
        repeated.values.collect().get_column("integer_value").sum(),
        repeated.findings.rows.collect().height,
        "`inflection.underscore` repeats 3 times across 2 files"
        in repeated.findings.rows.collect().item(0, "message"),
        [item.values.collect().get_column("integer_value").sum() for item in variants],
        variants[0].findings is not None and variants[0].findings.rows.collect().is_empty(),
    ) == (3, 1, True, [0, 0, 0], True)


def test_deployment_reproducibility_cases() -> None:
    complete = fact(
        DeploymentFact,
        locked_inputs=["chefe.lock"],
        build_command="chefe run build",
        environment="linux-aarch64",
        artifact_identity="sha256:abc",
        migrations=["migrations/001.sql"],
        configuration_sources=["settings.toml"],
        secrets_boundary="runtime environment",
        rollback_command="chefe run rollback",
        provenance="attestation.json",
    )
    assert answer(deployment_reproducibility, complete).value == "reproducible"
    assert (
        answer(
            deployment_reproducibility,
            complete.model_copy(
                update={
                    "build_command": "",
                    "environment": "",
                    "artifact_identity": "",
                    "migrations": [],
                    "configuration_sources": [],
                    "secrets_boundary": "",
                    "rollback_command": "",
                    "provenance": "",
                }
            ),
        )
    ).value == "partial"
    assert (
        answer(
            deployment_reproducibility,
            DeploymentFact(key="empty", span=_SPAN),
        )
    ).value == "nonreproducible"
    assert answer(deployment_reproducibility, complete, require_provenance=False).value == (
        "reproducible"
    )
    assert (
        answer(
            deployment_reproducibility,
            complete.model_copy(update={"is_applicable": False}),
        )
    ).value == "not_applicable"


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
    assert answer(repeated_class_method_count, methods).value == 2

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
    assert answer(repeated_semantic_string_literal, strings).value == 1


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
                tested_states=["enabled", "disabled"],
                cleanup_plan="remove when authorization migrates",
            ),
            FeatureFlag(name="expired", age_days=1, decision_due_days=0),
        ],
    )
    assert answer(feature_flag_debt, flags).value == 2

    quarantined = fact(
        QuarantineFact,
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
            QuarantinedTest(
                name="unknown age",
                owner="team",
                has_remediation_evidence=True,
            ),
        ],
    )
    assert answer(flaky_test_quarantine_debt, quarantined).value == 3

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
    assert answer(waiver_debt, waivers).value == 4


def test_string_expression_cases() -> None:
    subject = fact(
        StringExpressionFact,
        expressions=[
            LiteralStringExpression(
                runtime_value="first\nsecond",
                literal_fragment_count=2,
                node=NodeRef(id="literal", span=_SPAN, text='"first\\n" "second"'),
            ),
            LiteralStringExpression(
                runtime_value="one wrapped line",
                literal_fragment_count=3,
                wraps_single_runtime_line=True,
                node=NodeRef(id="wrapped", span=_SPAN),
            ),
            RepeatedStringExpression(
                literal="-", repetition_count=30, node=NodeRef(id="dash", span=_SPAN)
            ),
            RepeatedStringExpression(
                literal="=-", repetition_count=20, node=NodeRef(id="mixed", span=_SPAN)
            ),
            RepeatedStringExpression(
                literal="a", repetition_count=30, node=NodeRef(id="letter", span=_SPAN)
            ),
        ],
    )
    assert answer(fragmented_multiline_literal, subject).value == 1
    assert answer(decorative_repeated_separator_count, subject).value == 2

    python = subject.model_copy(update={"language": "python"})
    result = answer(fragmented_multiline_literal, python).query
    assert result.fix is not None
    assert result.fix.rewrites.collect().get_column("source").to_list() == ['"""first\nsecond"""']
    generic_fix = answer(fragmented_multiline_literal, subject).query.fix
    assert generic_fix is not None
    assert generic_fix.rewrites.collect().is_empty()


def test_authorship_signal_cases() -> None:
    """Only eligible exact matches from the selected external analyzers count."""
    matches = fact(
        AuthorshipSignalFact,
        matches=[
            AuthorshipMatch(
                segment="intro",
                provider="Pangram",
                provider_version="3",
                rule="ai-style",
                matched_text="At its core",
                span=SourceSpan(path="README.md", start_line=2),
            ),
            AuthorshipMatch(
                segment="intro",
                provider="Pangram",
                matched_text="delve",
                span=SourceSpan(path="README.md", start_line=3),
            ),
            AuthorshipMatch(
                segment="code",
                provider="Pangram",
                matched_text="robust",
                span=SourceSpan(path="README.md", start_line=8),
                is_eligible=False,
            ),
        ],
    )
    result = answer(ai_associated_pattern_count, matches)
    assert result.value == 2
    assert answer(ai_associated_pattern_count, matches, providers=["pangram"]).value == 2
    assert answer(ai_associated_pattern_count, matches, providers=["vale"]).value == 0
    assert result.query.findings is not None
    findings = result.query.findings.rows.collect()
    assert findings.get_column("path").to_list() == ["README.md", "README.md"]
    assert findings.get_column("start_line").to_list() == [2, 3]


def test_prose_distribution_cases() -> None:
    empty = LengthDistribution(root=[])
    measured = LengthDistribution.from_value([2, 4, 8])
    uniform = ProseSection(
        sentence_word_counts=LengthDistribution(root=[10, 10, 10, 10, 10]),
        paragraph_word_counts=LengthDistribution(root=[40, 40, 40, 40]),
        sentence_openers=["This", "This", "That", "Other", "This", "Another"],
    )
    varied = ProseSection(
        sentence_word_counts=LengthDistribution(root=[3, 5, 10, 20, 40]),
        paragraph_word_counts=LengthDistribution(root=[30, 45, 80, 120]),
        sentence_openers=["A", "I", "Each", "Different", "Word", "Starts"],
    )
    subject = fact(ProseSegmentFact, sections=[uniform, varied])
    assert (
        LengthDistribution.from_value(empty) is empty,
        len(empty),
        empty.uniformity(),
        len(measured),
        measured.at_least(4),
        measured.uniformity(),
        answer(sentence_length_uniformity, subject).value,
        answer(paragraph_length_uniformity, subject).value,
        answer(sentence_opener_concentration, subject).value,
        answer(sentence_opener_concentration, subject, ignored_openers=[]).value,
        answer(
            sentence_opener_concentration,
            subject.model_copy(update={"sections": []}),
        ).value,
    ) == (
        True,
        0,
        0.0,
        3,
        LengthDistribution(root=[4, 8]),
        pytest.approx(52.38095238095239),
        100.0,
        100.0,
        50.0,
        50.0,
        0.0,
    )
