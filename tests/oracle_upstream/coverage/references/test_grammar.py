from string import ascii_lowercase

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from mcmr.accounting.upstream import (
    Coverage,
    Inventory,
    Reference,
    ReferenceParser,
    Relation,
    ToolRegistry,
    UpstreamRule,
)

from ..support import inventoried


@pytest.mark.parametrize("tool", inventoried())
def test_the_grammar_round_trips_every_rule_a_tool_ships(tool: str) -> None:
    """Every identity in a frozen inventory survives being written down and read back.

    Sampling would have been enough to find the first defect here, which was Ruff's five-letter
    `ASYNC` prefix falling outside the code pattern, and reading the whole inventory is what proves
    there is no second one hiding behind a prefix nobody happened to draw.
    """
    profile = ToolRegistry().by_name[tool]
    parser = ReferenceParser()
    for rule in Inventory.load(tool).rules:
        upstream = UpstreamRule(tool=profile.name, code=rule.code, symbol=rule.symbol)
        for relation in Relation:
            written = Reference(text="", relation=relation, upstream=upstream).spelling
            parsed = parser.entry(written)
            assert parsed.upstream == upstream, written
            assert parsed.relation is relation, written
            assert parsed.text == written


@settings(max_examples=200, deadline=None)
@given(
    tokens=st.lists(
        st.text(alphabet=ascii_lowercase + "-_", min_size=1, max_size=12),
        min_size=1,
        max_size=6,
    )
)
def test_a_line_that_opens_on_no_relation_is_refused(tokens: list[str]) -> None:
    """The relation word is the only door into a reference, and there is no door beside it.

    Prose used to fall through this and become a citation of itself, which is how one book turned
    into several rows nobody could add up. A section holds references and nothing else now, so a
    sentence in it is a defect the parse states rather than a row the table invents.
    """
    assume(tokens[0] not in ReferenceParser().relations)

    with pytest.raises(ValueError, match="states neither a source nor a URL"):
        ReferenceParser().entry(" ".join(tokens))


@pytest.mark.parametrize(
    "line",
    [
        "",
        "Pylint",
        "Clippy no_effect",
        "Vulture documentation, unused code boundary",
        "Robert C. Martin, Clean Code, chapter 10, classes should be small",
        "Ruff and Pylint can count parents or detect invalid overrides. They do not prove that a",
        "Cites Fluent Python, chapter 5",
        'Cites "Fluent Python" chapter 5',
    ],
)
def test_prose_never_becomes_a_reference(line: str) -> None:
    """A tool named inside a sentence is prior art, and reading it as coverage would be a lie.

    The last two are the literature half of the same trap. An unquoted title reads exactly like a
    tool followed by an identity, and a locator with no comma before it reads like a second
    identity, so both are refused rather than guessed at.
    """
    with pytest.raises(ValueError, match="states neither a source nor a URL"):
        ReferenceParser().entry(line)


@pytest.mark.parametrize(
    "line",
    [
        "Adapts Pylint W0611 W0212",
        "Cites Clippy no_effect dbg_macro",
    ],
)
def test_a_relation_that_names_no_rule_is_rejected(line: str) -> None:
    """A reference the parser silently downgraded to prose is one nobody would ever see fail."""
    with pytest.raises(ValueError, match="without naming a rule"):
        ReferenceParser().entry(line)


def test_a_url_with_no_reference_above_it_is_rejected() -> None:
    """A URL attaches to the entry above it, so one with nothing above it attaches to nothing."""
    with pytest.raises(ValueError, match="URL with no reference above it"):
        ReferenceParser().parse(["https://example.invalid/page", "Cites Clippy no_effect"])


def test_a_url_line_carries_no_source_of_its_own() -> None:
    """A URL is where a reference points rather than a reference, so it names nothing by itself."""
    entry = ReferenceParser().entry("https://example.invalid/page")

    assert entry.spelling == ""
    assert entry.source == ""
    assert entry.lines == ["https://example.invalid/page"]


def test_a_citation_claims_nothing() -> None:
    """Only the two claiming relations reach the account, which is what keeps prior art out."""
    assert Relation.CITES.coverage is None
    assert Relation.CITES.word == "Cites"
    assert Relation.GENERALIZES.coverage is Coverage.NATIVE
    assert Relation.ADAPTS.coverage is Coverage.ADAPTED


def test_a_citation_cannot_be_read_as_an_upstream_claim() -> None:
    """Claim-only projections fail when a literature entry reaches them by mistake."""
    citation = Reference(relation=Relation.CITES, work="Clean Code")

    with pytest.raises(ValueError, match="does not claim"):
        _ = citation.coverage
    with pytest.raises(ValueError, match="does not name"):
        _ = citation.claimed_upstream
