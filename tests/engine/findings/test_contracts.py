from enum import StrEnum
from typing import TYPE_CHECKING

import pytest

from mcmr import Boolean, Category, MCMRConfiguration, Numeric, RulePolicies
from mcmr.commands.quality import Judgment
from mcmr.domain.contracts import ModelProvenance
from mcmr.execution import Classification, ClassificationBackend, ModelCandidate
from mcmr.facts import Evidence, FileHistory, FunctionFact, RepositoryHistoryFact, SourceSpan
from mcmr.plugins import fact_table
from mcmr.query import RuleQuery
from mcmr.rulebook.catalog import Catalog
from mcmr.rulebook.discovery import RuleModuleDiscovery
from mcmr.rules.general import large_file_the_team_keeps_reopening, primitive_obsession

from ...support import kernel_binary, needs_kernel, written
from .claims import assert_claim, claims
from .data import exemplars, fixture, wide_families

if TYPE_CHECKING:
    from mcmr.checking.session import Verdicts


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Verdicts:
    """Build every fact family the fixture project supports, once for the whole module."""
    stated = claims()
    root = written(tmp_path_factory.mktemp("findings"), fixture())
    definitions = {
        definition.id: definition
        for definition in Catalog(modules=RuleModuleDiscovery().modules).definitions
        if definition.id in {claim.rule for claim in stated}
    }
    policies = RulePolicies(
        overrides={
            rule_id: (
                Boolean()
                if definition.output == "bool"
                else Category(bad=set(definition.categories))
                if definition.output == "category"
                else Numeric(maximum=-1)
            )
            for rule_id, definition in definitions.items()
        },
    )
    return Judgment(
        binary=kernel_binary(),
        root=root,
        policies=policies,
        configuration=MCMRConfiguration(
            select=list(dict.fromkeys(claim.rule for claim in stated))
        ),
    ).run()


@needs_kernel
def test_every_migrated_rule_says_the_sentence_it_claims_about_the_fixture_project(
    project: Verdicts,
) -> None:
    """Each row is one rule's whole finding, read back off a repository written to provoke it.

    A finding has to name the right thing inside a file that also holds things the rule must stay
    quiet about, which is why this is one project rather than one snippet per rule. The message,
    the place, the numbers behind it, and whether the repair is the rule's own or the fix it
    already declares are all checked, since a finding right about three of those and wrong about
    the fourth is still a finding nobody can act on.
    """
    for claim in claims():
        assert_claim(project, claim)


def test_the_history_rule_names_the_file_and_what_keeps_bringing_people_back() -> None:
    """No repository this suite writes has a history, so the recorded evidence is stated here."""
    subject = RepositoryHistoryFact(
        key="history:shop",
        span=SourceSpan(path=".git"),
        unscoped_commit_count=40,
        files=[
            FileHistory(
                path="shop/service.py",
                author_count=6,
                additional_commit_count=24,
                line_count=620,
            ),
            FileHistory(
                path="shop/api.py", author_count=1, additional_commit_count=1, line_count=800
            ),
        ],
    )

    answer = large_file_the_team_keeps_reopening.invoke_table(
        fact_table(RepositoryHistoryFact, [subject]),
        settings={},
        dependencies={},
    )
    if not isinstance(answer, RuleQuery):
        raise TypeError("the history rule returned a model query")
    values = answer.values.collect()
    assert answer.findings is not None
    finding = answer.findings.rows.collect().row(0, named=True)

    assert (
        values.item(0, "integer_value"),
        finding["message"],
        finding["path"],
        finding["start_line"],
    ) == (
        1,
        "`shop/service.py` runs 620 lines and took 30 commits against the 30 the busiest file "
        "took, the last of them 0 days ago",
        "shop/service.py",
        1,
    )
    assert dict(
        zip(
            finding["measurement_names"],
            finding["measurement_values"],
            strict=True,
        )
    ) == {
        "lines": 620,
        "commits": 30,
        "commits the busiest file took": 30,
        "days since the last one": 0,
    }


class FirstCategory(ClassificationBackend):
    """Answer with the first category of whatever rubric a rule states."""

    async def classify_candidate[Category: StrEnum](
        self, candidate: ModelCandidate, *, category: type[Category], instructions: str
    ) -> Classification[Category]:
        """Return the first allowed category, which is all a lane test needs from a model."""
        assert instructions
        assert candidate.fact_id
        return Classification(
            value=next(iter(category)),
            reasoning="Controlled classification for contract verification.",
            evidence=list(candidate.retained),
            confidence=1.0,
            provenance=ModelProvenance(
                backend="controlled",
                model="test",
                reasoning_effort="none",
            ),
        )


@pytest.mark.anyio
async def test_the_model_lane_carries_the_claims_its_judgment_read() -> None:
    """A judgment nobody can reproduce is only worth reading beside the evidence it saw."""
    subject = FunctionFact(
        key="design:shop/service.py",
        span=SourceSpan(path="shop/service.py", start_line=4, end_line=30),
        conditional_count=1,
        parameters=[
            FunctionFact.Parameter(name="amount_minor", type_name="int"),
            FunctionFact.Parameter(name="currency", type_name="str"),
        ],
        evidence=[
            Evidence(signal="repeated_validation", detail="two sites", source="kernel"),
            Evidence(signal="parameter_group", detail="amount and currency", source="kernel"),
        ],
    )

    backend = FirstCategory()
    planned = primitive_obsession.invoke_table(
        fact_table(FunctionFact, [subject]),
        settings={},
        dependencies={ClassificationBackend: backend},
    )
    if isinstance(planned, RuleQuery):
        raise TypeError("the design rule returned a deterministic query")
    answer = await backend.resolve(planned)
    values = answer.values.collect()
    assert answer.findings is not None
    findings = answer.findings.normalized().rows.collect()

    assert (
        values.item(0, "category_value"),
        findings.height,
        findings.item(0, "message"),
        set(findings.get_column("path")),
        set(findings.get_column("start_line")),
        set(findings.get_column("end_line")),
        findings.get_column("measurement_names").to_list()[0],
        findings.get_column("measurement_values").to_list()[0],
        set(findings.get_column("provenance_backend")),
        all(
            evidence == ["repeated_validation", "parameter_group"]
            for evidence in findings.get_column("evidence").to_list()
        ),
        all(
            question.startswith("check `modeled` against")
            for question in findings.get_column("choice_question")
        ),
    ) == (
        "modeled",
        5,
        "`domain rules repeat` is `yes`. Controlled classification for contract verification.",
        {"shop/service.py"},
        {4},
        {30},
        ["criterion confidence"],
        [100.0],
        {"controlled"},
        True,
        True,
    )


def test_the_worked_examples_cover_every_shape_a_rule_can_take(catalog: Catalog) -> None:
    """Examples that drifted into one shape would stop proving the contract for the others.

    Each of these is a case the migration had to answer differently, so the recipe a following
    agent applies is only trustworthy while every one of them has a worked example in the tree.
    """
    examples = exemplars()
    wide = wide_families()
    migrated = [item for item in catalog.definitions if item.id in examples]
    covered = {
        "count": [item for item in migrated if item.output == "int"],
        "percentage": [item for item in migrated if item.output == "float"],
        "occurrence": [item for item in migrated if item.output == "bool" and item.unit],
        "bare boolean": [item for item in migrated if item.output == "bool" and not item.unit],
        "category": [item for item in migrated if item.output == "category"],
        "repository-wide fact": [item for item in migrated if item.fact in wide],
        "per-file fact": [item for item in migrated if item.fact not in wide],
        "carries an autofix": [item for item in migrated if item.fixes],
        "model lane": [item for item in migrated if item.lane != "deterministic"],
    }

    assert {shape for shape, found in covered.items() if not found} == set()
    assert all(reason for reason in examples.values())
