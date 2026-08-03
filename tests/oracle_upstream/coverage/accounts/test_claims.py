from typing import TYPE_CHECKING

import pytest

from mcmr.accounting.upstream import (
    ClaimIndex,
    Inventory,
    ReferenceParser,
    ToolProfile,
    ToolRegistry,
)
from mcmr.domain.contracts import RuleDefinition

from ..support import inventoried

if TYPE_CHECKING:
    from collections.abc import Sequence


@pytest.mark.parametrize("tool", inventoried())
def test_every_claim_names_a_rule_its_tool_actually_ships(tool: str, claims: ClaimIndex) -> None:
    """A reference to a rule a tool does not have is a defect, so it is a failure here."""
    inventory = Inventory.load(tool)
    name = ToolRegistry().by_name[tool].name
    codes = {rule.code for rule in inventory.rules if rule.code}
    symbols = {rule.symbol for rule in inventory.rules}
    wrong = {
        (claim.rule, upstream.code, upstream.symbol)
        for claim in claims.claims
        if (upstream := claim.upstream) is not None
        if upstream.tool == name
        and not (upstream.code in codes | {""} and upstream.symbol in symbols | {""})
    }

    assert not wrong, sorted(wrong)


@pytest.mark.parametrize("tool", inventoried())
def test_every_claim_matches_exactly_one_rule_of_the_inventory(
    tool: str, claims: ClaimIndex
) -> None:
    """A claim whose code and symbol name two different rules would cover neither of them."""
    inventory = Inventory.load(tool)
    name = ToolRegistry().by_name[tool].name
    stated = [
        (claim, upstream)
        for claim in claims.claims
        if (upstream := claim.upstream) is not None and upstream.tool == name
    ]
    matched = {
        (upstream.code, upstream.symbol): [
            rule
            for rule in inventory.rules
            if upstream.code in {"", rule.code} and upstream.symbol in {"", rule.symbol}
        ]
        for _, upstream in stated
    }

    assert all(len(found) == 1 for found in matched.values()), {
        key: len(found) for key, found in matched.items() if len(found) != 1
    }


def test_every_reference_parses_and_round_trips(definitions: Sequence[RuleDefinition]) -> None:
    """A grammar a docstring cannot be written back out of is a grammar nobody can trust."""
    parser = ReferenceParser()
    for definition in definitions:
        written = definition.documentation.references
        entries = parser.parse(written)
        assert [line for entry in entries for line in entry.lines] == written, definition.id


def test_every_named_reference_is_written_in_the_one_canonical_spelling(
    definitions: Sequence[RuleDefinition],
) -> None:
    """Two spellings of one reference is the drift this replaced a ledger to avoid."""
    parser = ReferenceParser()
    wrong = [
        (definition.id, entry.text, entry.spelling)
        for definition in definitions
        for entry in parser.parse(definition.documentation.references)
        if entry.upstream is not None and entry.text != entry.spelling
    ]

    assert not wrong, wrong


def test_every_rule_states_references_and_every_one_of_them_names_a_source(
    definitions: Sequence[RuleDefinition],
) -> None:
    """Provenance lives on the rule now, so the section it lives in is never empty.

    Both halves are counted here because the literature half used to be prose nobody could add up.
    Every entry names a registered tool rule or a registered work, and the two numbers close on the
    total, so a line that names neither cannot hide inside the section.
    """
    parser = ReferenceParser()
    sections = {
        definition.id: parser.parse(definition.documentation.references)
        for definition in definitions
    }

    assert set(sections) == {definition.id for definition in definitions}
    assert all(entries for entries in sections.values())
    entries = [entry for found in sections.values() for entry in found]
    named = [entry for entry in entries if entry.upstream]
    cited = [entry for entry in entries if entry.work]
    assert len(named) + len(cited) == len(entries)
    assert all(entry.source for entry in entries)


def test_a_named_reference_renders_a_link(definitions: Sequence[RuleDefinition]) -> None:
    """The docstrings feed a website, so every named rule has to reach the page documenting it."""
    registry = ToolRegistry()
    parser = ReferenceParser()
    links = [
        entry.url
        or registry.by_name[upstream.tool.casefold()].link(
            code=upstream.code,
            symbol=upstream.symbol,
        )
        for definition in definitions
        for entry in parser.parse(definition.documentation.references)
        if (upstream := entry.upstream) is not None
    ]

    assert links
    assert all(link.startswith("https://") for link in links)


def test_a_tool_that_documents_nothing_renders_no_link() -> None:
    """A profile with no page to point at says so instead of building a broken URL."""
    profile = ToolProfile(name="Cppcheck")

    assert profile.link(code="", symbol="nullPointer") == ""


def test_a_link_is_built_from_the_code_the_symbol_and_the_category() -> None:
    """Each tool spells its own page differently, and the template is what absorbs that."""
    registry = ToolRegistry()

    assert (
        registry.by_name["pylint"]
        .link(code="R0904", symbol="too-many-public-methods")
        .endswith("/refactor/too-many-public-methods.html")
    )
    assert (
        registry.by_name["clang-tidy"]
        .link(code="", symbol="bugprone-unused-return-value")
        .endswith("/checks/bugprone/unused-return-value.html")
    )
    assert registry.of("CLIPPY") is registry.by_name["clippy"]
    assert registry.of("cppcheck") is registry.by_name["cppcheck"]
    assert (
        registry.by_name["cppcheck"].link(code="", symbol="nullPointer").endswith("/manual.html")
    )
