from typing import TYPE_CHECKING, cast

import pytest

from mcmr.domain.contracts import RuleLane, RuleScope
from mcmr.facts import CallFact, ClassFact, FunctionFact, ImportBindingFact, SyntaxFact, buildable
from mcmr.query import RuleQuery
from mcmr.table import AnalysisSession

from ..support import needs_kernel
from .coverage.support import language_fixtures, language_suffixes

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from mcmr.domain.contracts import RuleContract
    from mcmr.plugins import Fact, Table
    from mcmr.rulebook.catalog import Catalog


_REFERENCE = "python"

# General rules missing from another language are recorded with their reason.

# Family coverage cannot catch a frontend that fills `FunctionFact` but leaves
# `control_increments` empty. That once scored the same program as 16 in Python and 0 elsewhere.

# Comparing rules over one program written six ways exposes that hole. A reference-only result
# needs a provider fix or a written language difference.

# The reverse is not a defect because a rule finding more outside the reference language works.
_GAPS: dict[str, dict[str, str]] = {
    "ALL-CLAS0005": {
        "c": "the rule compares the last dotted component of a resolved base against the name the "
        "source wrote, and every other language separates a qualified name some other way, so it "
        "reads a match only for the reference language",
        "cpp": "the same",
        "cuda": "the same",
        "rust": "the same, where the base arrives as `crate::sample::Base`",
    },
    "ALL-REAC0002": {
        "c": "a header and its translation unit are one module, so the fixture declares nothing "
        "this file reads and no other file does"
    },
}


@pytest.fixture(scope="module")
def repositories(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Write one small repository per language, each stating the same program."""
    written = {}
    for language, (name, source) in language_fixtures().items():
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
    selected = {families[name] for _, name, _ in general(catalog)}
    session = AnalysisSession(
        root,
        suffixes=language_suffixes()[language],
        typed_families=sorted(selected, key=lambda family: family.__name__),
    )
    tables: dict[str, Table[Fact]] = {
        name: family_table(session, family)
        for name, family in families.items()
        if family in selected
    }
    return {
        rule_id for rule_id, family, rule in general(catalog) if has_findings(rule, tables[family])
    }


def family_table(session: AnalysisSession, family: type[Fact]) -> Table[Fact]:
    """Move one selected native table through its specialized or generic boundary."""
    specialized: dict[type[Fact], Callable[[], Table[Fact]]] = {
        FunctionFact: lambda: cast("Table[Fact]", session.function_tables()),
        CallFact: lambda: cast("Table[Fact]", session.call_tables()),
        ClassFact: lambda: cast("Table[Fact]", session.class_tables()),
        ImportBindingFact: lambda: cast("Table[Fact]", session.import_binding_tables()),
        SyntaxFact: lambda: cast("Table[Fact]", session.syntax_tables()),
    }
    factory = specialized.get(family)
    return session.table(family) if factory is None else factory()


def has_findings(rule: RuleContract, table: Table[Fact]) -> bool:
    """Invoke one general rule once and report whether a numeric scalar is positive."""
    result = rule.invoke_table(table, settings={}, dependencies={})
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic parity rule returned a model query")
    values = result.values.collect()
    return any(
        item > 0
        for column in ("boolean_value", "integer_value", "float_value")
        for item in values.get_column(column).drop_nulls()
    )


@needs_kernel
@pytest.mark.parametrize("language", sorted(set(language_fixtures()) - {_REFERENCE}))
def test_a_general_rule_that_answers_for_one_language_answers_for_every_language(
    language: str, repositories: Mapping[str, Path], catalog: Catalog
) -> None:
    """One rule answering for every language is the whole claim, so it is checked rather than said.

    Python is the reference frontend, so whatever it finds is what a general rule was written
    against. A rule finding nothing for another language over the same program reports zero there
    forever, which a reader cannot tell apart from a clean repository, so the difference has to be
    written into `GAPS` with its reason rather than discovered later by somebody trusting the
    catalog.
    """
    reference = findings(catalog, repositories[_REFERENCE], _REFERENCE)
    excused = {rule_id for rule_id in reference if language in _GAPS.get(rule_id, {})}

    assert reference - findings(catalog, repositories[language], language) == excused


def test_every_recorded_difference_names_a_general_rule_and_says_why(catalog: Catalog) -> None:
    """The ledger cannot outlive the gap it records, and cannot invent one either."""
    known = {rule_id for rule_id, _, _ in general(catalog)}

    assert set(_GAPS) <= known
    assert all(
        set(languages) <= set(language_fixtures()) - {_REFERENCE} for languages in _GAPS.values()
    )
    assert all(reason for languages in _GAPS.values() for reason in languages.values())
