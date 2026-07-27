import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from mcmr.catalog import Catalog
from mcmr.discovery import RuleModuleDiscovery
from mcmr.influence import Influence, InfluenceReport
from mcmr.models import RuleDefinition
from mcmr.upstream import (
    ClaimIndex,
    Reference,
    ReferenceParser,
    Relation,
    SourceKind,
    Work,
    WorkRegistry,
)

# A locator is free text a reader reads, so the only shapes it may not take are the ones the
# grammar reserves. It stays on one line and it may not open with a space the comma already wrote.
LOCATORS = st.text(
    alphabet=st.characters(exclude_characters="\n\r", categories=("L", "N", "P", "Zs")),
    min_size=1,
    max_size=60,
).map(str.strip)


@pytest.fixture(scope="module")
def definitions() -> tuple[RuleDefinition, ...]:
    """Return every rule the catalog validates, which is where provenance lives."""
    return tuple(Catalog(modules=RuleModuleDiscovery().modules).definitions)


@pytest.fixture(scope="module")
def registry() -> WorkRegistry:
    """Return the registry of works this package ships."""
    return WorkRegistry.load()


@pytest.fixture(scope="module")
def report(definitions: tuple[RuleDefinition, ...]) -> InfluenceReport:
    """Return the influence table derived from what those rules say about themselves."""
    return InfluenceReport(index=ClaimIndex(definitions=definitions))


def test_every_reference_the_catalog_states_resolves_to_one_registered_source(
    report: InfluenceReport, definitions: tuple[RuleDefinition, ...]
) -> None:
    """The whole point is that the table is counted rather than estimated.

    Every reference resolves or the parse fails, so the sum of the rows is the number of references
    the catalog states and nothing was dropped on the way into the table.
    """
    stated = sum(len(definition.documentation.references) for definition in definitions)
    urls = sum(bool(reference.url) for _, reference in report.index.references)

    assert sum(row.references for row in report.rows) == stated - urls
    assert sum(row.references for row in report.rows) == 825
    assert len(report.rows) == 201


def test_no_registered_work_is_cited_by_nothing(report: InfluenceReport) -> None:
    """A work nobody cites is a row stating an influence the catalog does not have."""
    assert report.uncited == ()


def test_the_registry_fails_on_a_work_no_rule_cites(
    report: InfluenceReport, registry: WorkRegistry
) -> None:
    """The guard runs in the stale direction, which is the one a table quietly rots in.

    Verified by adding an entry rather than by trusting the reading. A registry that only grew
    would keep every work anybody ever removed a citation of, and the table would report an
    influence that is no longer there.
    """
    invented = Work(title="A Book Nobody Opened", kind=SourceKind.BOOK)
    stale = WorkRegistry(works=(*registry.works, invented))

    grown = InfluenceReport(index=report.index, works=stale)

    assert grown.uncited == ("A Book Nobody Opened",)
    assert len(grown.rows) == len(report.rows)


def test_the_registry_fails_on_a_reference_naming_no_registered_work(
    definitions: tuple[RuleDefinition, ...], registry: WorkRegistry
) -> None:
    """The guard runs in the live direction too, which is the one that invents a row.

    Verified by removing a work the catalog actually cites. Without this a title nobody registered
    would become its own entry, which is exactly how one book arrived twice under two spellings.
    """
    thinned = WorkRegistry(
        works=tuple(work for work in registry.works if work.title != "Refactoring")
    )
    parser = ReferenceParser(works=thinned)

    with pytest.raises(ValueError, match="which no registered work titles"):
        for definition in definitions:
            parser.parse(definition.documentation.references)


def test_the_table_names_the_work_rather_than_the_author(report: InfluenceReport) -> None:
    """The question is which work shaped the catalog, so a person is never a row.

    Ousterhout is the largest literature influence and appears under his book's title, with his
    name beside it as the display detail a citation renders rather than as the key it groups by.
    """
    books = report.of(SourceKind.BOOK)

    assert books[0].source == "A Philosophy of Software Design"
    assert books[0].author == "John Ousterhout"
    assert books[0].references == 32
    assert books[0].rules == 32
    assert books[0].citation == "A Philosophy of Software Design, John Ousterhout"
    assert not any(row.source == row.author for row in report.rows)


def test_the_tool_half_is_present_and_told_apart_by_its_kind(report: InfluenceReport) -> None:
    """Both halves belong in one table, and a linter is not a book.

    The tool rows are the same references the coverage account reads, so the two views of the same
    provenance agree by construction rather than by a number kept in two places.
    """
    tools = report.of(SourceKind.TOOL)
    named = sum(1 for _, reference in report.index.references if reference.upstream)

    assert sum(row.references for row in tools) == named == 117
    assert [row.source for row in tools[:3]] == ["Ruff", "Pylint", "Clippy"]
    assert all(not row.author and not row.link for row in tools)


def test_every_kind_holds_something_and_the_kinds_account_for_every_row(
    report: InfluenceReport,
) -> None:
    """A kind nobody uses is a kind nobody needs, and the arithmetic has to close."""
    tally = report.tally()

    assert sum(tally.values()) == len(report.rows)
    assert all(count for count in tally.values()), tally
    assert tally == {
        SourceKind.BOOK: 43,
        SourceKind.PAPER: 18,
        SourceKind.STANDARD: 37,
        SourceKind.LANGUAGE: 20,
        SourceKind.DOCUMENTATION: 62,
        SourceKind.ARTICLE: 12,
        SourceKind.TOOL: 9,
    }


def test_the_table_is_ordered_by_how_much_of_the_catalog_rests_on_a_source(
    report: InfluenceReport,
) -> None:
    """A table nobody can read top down answers nothing, so the order is part of the contract."""
    keys = [(-row.references, -row.rules, row.source) for row in report.rows]

    assert keys == sorted(keys)
    assert all(row.rules <= row.references for row in report.rows)
    assert report.rows[0].source == "The Python Standard Library"


def test_every_registered_work_carries_what_a_page_needs_to_cite_it(
    registry: WorkRegistry,
) -> None:
    """These feed a public site, so a work with no link is a citation nobody can follow."""
    assert len(registry.works) == 192
    assert all(work.link.startswith("http") for work in registry.works)
    assert all(work.title.strip() == work.title for work in registry.works)
    assert len({work.title for work in registry.works}) == len(registry.works)
    assert not [work for work in registry.works if work.kind is SourceKind.TOOL]


def test_a_source_belonging_to_neither_registry_has_no_row(report: InfluenceReport) -> None:
    """A row the table cannot describe would carry a title and nothing else, so it is refused."""
    with pytest.raises(ValueError, match="neither a registered work nor a registered tool"):
        report.row("Unknown checker", ("ALL-ARCH0011",))


def test_a_work_without_an_author_cites_as_its_title_alone() -> None:
    """Not every work has a person behind it, and a trailing comma would read as a missing name."""
    anonymous = Work(title="The Twelve-Factor App", kind=SourceKind.DOCUMENTATION)
    row = Influence(source="JSON Schema", kind=SourceKind.STANDARD, references=1, rules=1)

    assert anonymous.citation == "The Twelve-Factor App"
    assert row.citation == "JSON Schema"


@settings(
    max_examples=300, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(data=st.data(), relation=st.sampled_from(Relation), locator=LOCATORS)
def test_a_work_reference_round_trips_through_its_one_spelling(
    registry: WorkRegistry, data: st.DataObject, relation: Relation, locator: str
) -> None:
    """A grammar a docstring cannot be written back out of is a grammar nobody can trust."""
    title = data.draw(st.sampled_from([work.title for work in registry.works]))
    written = Reference(relation=relation, work=title, locator=locator).spelling

    parsed = ReferenceParser(works=registry).entry(written)

    assert parsed.work == title
    assert parsed.locator == locator
    assert parsed.relation is relation
    assert parsed.text == written
    assert parsed.spelling == written


@settings(
    max_examples=200, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    data=st.data(),
    author=st.text(alphabet=st.characters(categories=("L",)), min_size=1, max_size=20),
)
def test_an_author_written_beside_the_title_is_not_a_reference(
    registry: WorkRegistry, data: st.DataObject, author: str
) -> None:
    """One work is one identity because the syntax says so, not because a table maps spellings.

    `Luciano Ramalho, Fluent Python` and `Fluent Python, chapter 5` used to be two rows for one
    book. The first shape no longer parses at all and the second states its chapter inside the
    locator, so there is nothing left for an alias table to reconcile.
    """
    title = data.draw(st.sampled_from([work.title for work in registry.works]))
    parser = ReferenceParser(works=registry)

    with pytest.raises(ValueError, match="states neither a source nor a URL"):
        parser.entry(f'Cites {author}, "{title}"')
    assert parser.entry(f'Cites "{title}"').work == title


@settings(
    max_examples=200, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(title=st.text(alphabet=st.characters(exclude_characters='"\n\r'), min_size=1, max_size=40))
def test_a_title_the_registry_does_not_hold_is_refused(registry: WorkRegistry, title: str) -> None:
    """An unregistered work becoming its own row is the guesswork this replaced."""
    parser = ReferenceParser(works=registry)
    if registry.of(title) is not None:
        pytest.skip("the drawn title is one the registry holds")

    with pytest.raises(ValueError, match="which no registered work titles"):
        parser.entry(f'Cites "{title}"')
