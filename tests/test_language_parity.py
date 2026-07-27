from typing import TYPE_CHECKING

import pytest

from mcmr.kernel import Kernel, buildable
from mcmr.models import RuleLane, RuleScope, answered
from tests.conftest import BINARY, needs_kernel, synchronous
from tests.test_language_coverage import FIXTURES, SUFFIXES

if TYPE_CHECKING:
    from pathlib import Path

    from mcmr.catalog import Catalog
    from mcmr.facts import Fact
    from mcmr.models import RuleContract


REFERENCE = "python"

# Which general rules answer for the reference language and not for another, each with the reason.
#
# This is the guard the family-level coverage test could not be. That one asks whether a frontend
# fills `FunctionFact` at all, and every frontend does, so `control_increments` could be a field
# only Python ever wrote while the whole catalog read as covered. Cognitive complexity then scored
# 16 for the reference program and 0 for the same program in four other languages, which is the
# answer a clean repository gives and nothing in the suite could tell the two apart.
#
# So this compares the rules rather than the families. Over one program written six ways, a general
# rule that finds something for the reference language and nothing for another is either a hole in
# that frontend or a difference worth writing down. The other direction is not a defect, because a
# rule finding more elsewhere is a rule that works.
GAPS: dict[str, dict[str, str]] = {
    "ALL-CLAS0009": {
        "c": "the rule compares the last dotted component of a resolved base against the name the "
        "source wrote, and every other language separates a qualified name some other way, so it "
        "reads a match only for the reference language",
        "cpp": "the same",
        "cuda": "the same",
        "rust": "the same, where the base arrives as `crate::sample::Base`",
    },
    "ALL-COMM0002": {"typescript": "the TypeScript frontend states no comment family yet"},
    "ALL-COMM0005": {"typescript": "the same"},
    "ALL-COMM0006": {"typescript": "the same"},
    "ALL-REAC0002": {
        "c": "a header and its translation unit are one module, so the fixture declares nothing "
        "this file reads and no other file does"
    },
}


@pytest.fixture(scope="module")
def repositories(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Write one small repository per language, each stating the same program."""
    written = {}
    for language, (name, source) in FIXTURES.items():
        root = tmp_path_factory.mktemp(f"parity-{language}")
        (root / name).write_text(source)
        written[language] = root
    return written


def general(catalog: Catalog) -> list[tuple[str, str, RuleContract]]:
    """Return every general deterministic rule, as its identifier, its family, and its callable."""
    families = buildable()
    return [
        (
            definition.id,
            definition.fact,
            next(item for item in catalog.rules if item.callable_path == definition.callable),
        )
        for definition in catalog.definitions
        if definition.scope is RuleScope.GENERAL
        and definition.lane == RuleLane.DETERMINISTIC
        and definition.fact in families
    ]


def findings(catalog: Catalog, root: Path, language: str) -> set[str]:
    """Return every general rule that finds something in one language's copy of the program.

    A rule answers with a number, a Boolean, a share, or a category, and only the first three say
    whether anything was found. A category names a state rather than a quantity, so it is read out
    rather than compared as though zero meant silence.
    """
    families = buildable()
    workspace = Kernel(binary=BINARY, root=root, suffixes=SUFFIXES[language]).build(
        sorted(families), families
    )
    streams: dict[str, list[Fact]] = {
        name: workspace.stream(family) for name, family in families.items()
    }
    return {
        rule_id
        for rule_id, family, rule in general(catalog)
        for value in (
            [
                answered(synchronous(rule.invoke(fact, settings={}, dependencies={})))
                for fact in streams[family]
            ],
        )
        if any(item > 0 for item in value if isinstance(item, bool | int | float))
    }


@needs_kernel
@pytest.mark.parametrize("language", sorted(set(FIXTURES) - {REFERENCE}))
def test_a_general_rule_that_answers_for_one_language_answers_for_every_language(
    language: str, repositories: dict[str, Path], catalog: Catalog
) -> None:
    """One rule answering for every language is the whole claim, so it is checked rather than said.

    Python is the reference frontend, so whatever it finds is what a general rule was written
    against. A rule finding nothing for another language over the same program reports zero there
    forever, which a reader cannot tell apart from a clean repository, so the difference has to be
    written into `GAPS` with its reason rather than discovered later by somebody trusting the
    catalog.
    """
    reference = findings(catalog, repositories[REFERENCE], REFERENCE)
    excused = {rule_id for rule_id in reference if language in GAPS.get(rule_id, {})}

    assert reference - findings(catalog, repositories[language], language) == excused


def test_every_recorded_difference_names_a_general_rule_and_says_why(catalog: Catalog) -> None:
    """The ledger cannot outlive the gap it records, and cannot invent one either."""
    known = {rule_id for rule_id, _, _ in general(catalog)}

    assert set(GAPS) <= known
    assert all(set(languages) <= set(FIXTURES) - {REFERENCE} for languages in GAPS.values())
    assert all(reason for languages in GAPS.values() for reason in languages.values())
