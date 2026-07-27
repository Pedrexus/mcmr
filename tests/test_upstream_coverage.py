import re
import shutil
from string import ascii_lowercase
from typing import TYPE_CHECKING

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from mcmr.catalog import Catalog
from mcmr.discovery import RuleModuleDiscovery
from mcmr.inventories import FrozenInventories
from mcmr.models import RuleDefinition, RuleScope
from mcmr.upstream import (
    ClaimIndex,
    Coverage,
    GapAccount,
    Inventory,
    Reference,
    ReferenceParser,
    Relation,
    ToolCoverage,
    ToolProfile,
    ToolRegistry,
    ToolRule,
    UpstreamRule,
)

if TYPE_CHECKING:
    from pathlib import Path

INVENTORIED = tuple(profile.slug for profile in ToolRegistry().profiles if profile.inventoried)
INVENTORY_SIZES = {
    "pylint": 389,
    "ruff": 968,
    "clippy": 809,
    "clang-tidy": 604,
    "eslint": 292,
    "typescript-eslint": 134,
    "cppcheck": 342,
}


@pytest.fixture(scope="module")
def definitions() -> tuple[RuleDefinition, ...]:
    """Return every rule the catalog validates, which is where provenance now lives."""
    return tuple(Catalog(modules=RuleModuleDiscovery().modules).definitions)


@pytest.fixture(scope="module")
def claims(definitions: tuple[RuleDefinition, ...]) -> ClaimIndex:
    """Return every coverage claim read back out of those rules' own docstrings."""
    return ClaimIndex(definitions=definitions)


@pytest.fixture(scope="module")
def report(claims: ClaimIndex) -> ToolCoverage:
    """Return the Pylint account, which is the one with a written gap for every message."""
    return ToolCoverage(tool="pylint", claims=claims)


def test_every_rule_the_inventory_holds_is_accounted_for(report: ToolCoverage) -> None:
    """A tool claiming to supersede another owes an entry for every rule it emits."""
    assert len(report.entries) == len(report.inventory.rules)
    assert len(report.inventory.rules) == 389
    assert {entry.rule.code for entry in report.entries} == {
        rule.code for rule in report.inventory.rules
    }


@pytest.mark.parametrize("tool", INVENTORIED)
def test_every_registered_inventory_has_an_account(tool: str, claims: ClaimIndex) -> None:
    """Every frozen registry loads beside a written answer for each rule it ships."""
    report = ToolCoverage(tool=tool, claims=claims)

    assert set(INVENTORIED) == set(INVENTORY_SIZES)
    assert len(report.inventory.rules) == INVENTORY_SIZES[tool]
    assert len(report.entries) == INVENTORY_SIZES[tool]
    assert all(entry.reason.endswith(".") for entry in report.entries)


def test_every_entry_states_a_reason(report: ToolCoverage) -> None:
    """An unexplained verdict is worse than no verdict, since it reads as a decision."""
    assert all(len(entry.reason) > 40 for entry in report.entries)
    assert all(entry.reason.endswith(".") for entry in report.entries)


def test_a_covered_entry_names_the_rules_that_answer_it(report: ToolCoverage) -> None:
    """Coverage without a rule behind it is an assertion rather than an account."""
    answered = [
        entry for entry in report.entries if entry.coverage in {Coverage.NATIVE, Coverage.ADAPTED}
    ]

    assert len(answered) == 28
    assert all(entry.rules for entry in answered)
    assert all(not entry.rules for entry in report.entries if entry not in answered)


def test_a_claim_over_a_python_message_names_a_rule_that_could_answer_one(
    definitions: tuple[RuleDefinition, ...], claims: ClaimIndex
) -> None:
    """Every Pylint message is about Python, so a TypeScript rule can never be the answer.

    This caught three wrong mappings the day the account was first checked: `unused-import` and
    `misplaced-future` pointed at each other's rules, and `wildcard-import` pointed at a TypeScript
    rule. A claim that merely names an existing identifier is not a checked claim, and turning the
    provenance around does not make one, so the scope of the claiming rule is still checked here.
    """
    by_id = {definition.id: definition for definition in definitions}
    answerable = {RuleScope.GENERAL, RuleScope.PYTHON}
    wrong = {
        (claim.upstream.symbol, claim.rule)
        for claim in claims.claims
        if claim.upstream.tool == "Pylint" and by_id[claim.rule].scope not in answerable
    }

    assert not wrong, sorted(wrong)


def test_every_claim_covers_the_language_boundary_of_its_tool(claims: ClaimIndex) -> None:
    """A language-specific rule cannot answer an inventory spanning another language."""
    registry = ToolRegistry()
    wrong = {
        (claim.upstream.tool, claim.rule, claim.scope)
        for claim in claims.claims
        if not claim.covers(registry.by_name[claim.upstream.tool.casefold()])
    }

    assert not wrong, sorted(wrong)


def test_no_rule_is_claimed_and_gapped_at_once(report: ToolCoverage, claims: ClaimIndex) -> None:
    """A message a rule claims and the account also delegates would give two different answers.

    The old ledger hit this the moment a rule was named natively while sitting in the set of
    messages delegated to Ruff. The two halves now live apart, one on the rule and one beside the
    inventory, so the only thing keeping them disjoint is this.
    """
    claimed = {
        rule.symbol
        for rule in report.inventory.rules
        if claims.of("Pylint", rule.code, rule.symbol)
    }
    gapped = set(report.account.by_symbol)

    assert not claimed & gapped, sorted(claimed & gapped)


def test_an_inapplicable_message_is_about_pylint_rather_than_about_code(
    report: ToolCoverage,
) -> None:
    """This state exists to stop `we cannot` and `there is nothing here` reading as one number.

    Every entry in it has to be a message Pylint emits about its own run or its own configuration,
    which is the `main` checker plus the one informational message asking a pragma to spell a
    message by name. Anything else landing here would be a real gap wearing a comfortable label,
    so the membership is pinned rather than trusted.
    """
    inapplicable = [entry for entry in report.entries if entry.coverage is Coverage.INAPPLICABLE]

    assert len(inapplicable) == 19
    assert {entry.rule.group for entry in inapplicable} == {"main", "miscellaneous"}
    assert [entry.rule.symbol for entry in inapplicable if entry.rule.group != "main"] == [
        "use-symbolic-message-instead"
    ]
    assert not any(entry.rules for entry in inapplicable)


def test_every_state_holds_something_and_the_five_of_them_account_for_everything(
    report: ToolCoverage,
) -> None:
    """A state nobody uses is a state nobody needs, and the arithmetic has to close."""
    tally = report.tally()

    assert sum(tally.values()) == len(report.inventory.rules)
    assert all(count for count in tally.values()), tally
    assert tally == {
        Coverage.NATIVE: 22,
        Coverage.DELEGATED: 269,
        Coverage.ADAPTED: 6,
        Coverage.INAPPLICABLE: 19,
        Coverage.UNAVAILABLE: 73,
    }


def test_a_message_pylint_adds_later_is_reported_as_unaccounted(report: ToolCoverage) -> None:
    """A silent default would let a new Pylint release look covered on the day it lands."""
    invented = ToolRule(code="Z9999", symbol="brand-new-message", group="invented")

    entry = report.entry(invented)

    assert entry.coverage is Coverage.UNAVAILABLE
    assert "unaccounted" in entry.reason


@pytest.mark.parametrize("tool", INVENTORIED)
def test_no_gap_statement_is_dead(tool: str) -> None:
    """A gap naming a symbol or a group no release emits reads as an account and settles nothing.

    Two entries once sat in the delegation set from a Pylint that had since dropped them, and
    nothing noticed because a statement with no message behind it never reaches the account at all.
    """
    inventory = Inventory.load(tool)
    account = GapAccount.load(tool)
    symbols = {rule.symbol for rule in inventory.rules}
    groups = {rule.group for rule in inventory.rules}

    assert set(account.by_symbol) <= symbols, sorted(set(account.by_symbol) - symbols)
    assert set(account.by_group) <= groups, sorted(set(account.by_group) - groups)


def test_group_accounts_state_why_rules_are_not_gaps() -> None:
    """Retired, formatted, platform-specific, and run-only groups keep distinct answers."""
    assert GapAccount.load("eslint").by_group["deprecated"].coverage is Coverage.INAPPLICABLE
    assert GapAccount.load("eslint").by_group["layout"].coverage is Coverage.DELEGATED
    assert (
        GapAccount.load("typescript-eslint").by_group["deprecated"].coverage
        is Coverage.INAPPLICABLE
    )
    clang = GapAccount.load("clang-tidy")
    assert set(clang.by_group) == {
        "abseil",
        "android",
        "boost",
        "darwin",
        "fuchsia",
        "linuxkernel",
        "llvm",
        "llvmlibc",
        "mpi",
        "objc",
        "openmp",
        "zircon",
    }
    assert set(clang.by_group.values()) == {clang.gaps[0]}
    assert GapAccount.load("cppcheck").by_group["information"].coverage is Coverage.INAPPLICABLE


@pytest.mark.parametrize("tool", INVENTORIED)
def test_every_claim_names_a_rule_its_tool_actually_ships(tool: str, claims: ClaimIndex) -> None:
    """A reference to a rule a tool does not have is a defect, so it is a failure here."""
    inventory = Inventory.load(tool)
    name = ToolRegistry().by_name[tool].name
    codes = {rule.code for rule in inventory.rules if rule.code}
    symbols = {rule.symbol for rule in inventory.rules}
    wrong = {
        (claim.rule, claim.upstream.code, claim.upstream.symbol)
        for claim in claims.claims
        if claim.upstream.tool == name
        and not (claim.upstream.code in codes | {""} and claim.upstream.symbol in symbols | {""})
    }

    assert not wrong, sorted(wrong)


@pytest.mark.parametrize("tool", INVENTORIED)
def test_every_claim_matches_exactly_one_rule_of_the_inventory(
    tool: str, claims: ClaimIndex
) -> None:
    """A claim whose code and symbol name two different rules would cover neither of them."""
    inventory = Inventory.load(tool)
    name = ToolRegistry().by_name[tool].name
    stated = [claim for claim in claims.claims if claim.upstream.tool == name]
    matched = {
        (claim.upstream.code, claim.upstream.symbol): [
            rule
            for rule in inventory.rules
            if claim.upstream.code in {"", rule.code}
            and claim.upstream.symbol in {"", rule.symbol}
        ]
        for claim in stated
    }

    assert all(len(found) == 1 for found in matched.values()), {
        key: len(found) for key, found in matched.items() if len(found) != 1
    }


def test_every_reference_parses_and_round_trips(definitions: tuple[RuleDefinition, ...]) -> None:
    """A grammar a docstring cannot be written back out of is a grammar nobody can trust."""
    parser = ReferenceParser()
    for definition in definitions:
        written = definition.documentation.references
        entries = parser.parse(written)
        assert [line for entry in entries for line in entry.lines] == written, definition.id


def test_every_named_reference_is_written_in_the_one_canonical_spelling(
    definitions: tuple[RuleDefinition, ...],
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
    definitions: tuple[RuleDefinition, ...],
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

    assert len(sections) == 277
    assert all(entries for entries in sections.values())
    entries = [entry for found in sections.values() for entry in found]
    named = [entry for entry in entries if entry.upstream]
    cited = [entry for entry in entries if entry.work]
    assert len(entries) == 825
    assert len(named) == 117
    assert len(cited) == 708
    assert all(entry.source for entry in entries)


def test_a_named_reference_renders_a_link(definitions: tuple[RuleDefinition, ...]) -> None:
    """The docstrings feed a website, so every named rule has to reach the page documenting it."""
    registry = ToolRegistry()
    parser = ReferenceParser()
    links = [
        entry.url or registry.by_name[entry.upstream.tool.casefold()].link(entry.upstream)
        for definition in definitions
        for entry in parser.parse(definition.documentation.references)
        if entry.upstream is not None
    ]

    assert links
    assert all(link.startswith("https://") for link in links)


def test_a_tool_that_documents_nothing_renders_no_link() -> None:
    """A profile with no page to point at says so instead of building a broken URL."""
    profile = ToolProfile(name="Cppcheck")

    assert profile.link(UpstreamRule(tool="Cppcheck", symbol="nullPointer")) == ""


def test_a_link_is_built_from_the_code_the_symbol_and_the_category() -> None:
    """Each tool spells its own page differently, and the template is what absorbs that."""
    registry = ToolRegistry()

    assert (
        registry.by_name["pylint"]
        .link(UpstreamRule(tool="Pylint", code="R0904", symbol="too-many-public-methods"))
        .endswith("/refactor/too-many-public-methods.html")
    )
    assert (
        registry.by_name["clang-tidy"]
        .link(UpstreamRule(tool="clang-tidy", symbol="bugprone-unused-return-value"))
        .endswith("/checks/bugprone/unused-return-value.html")
    )
    assert registry.of("CLIPPY") is registry.by_name["clippy"]
    assert registry.of("cppcheck") is registry.by_name["cppcheck"]
    assert (
        registry.by_name["cppcheck"]
        .link(UpstreamRule(tool="cppcheck", symbol="nullPointer"))
        .endswith("/manual.html")
    )


@pytest.mark.parametrize("tool", INVENTORIED)
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
    assert entry.lines == ("https://example.invalid/page",)


def test_a_citation_claims_nothing() -> None:
    """Only the two claiming relations reach the account, which is what keeps prior art out."""
    assert Relation.CITES.coverage is None
    assert Relation.CITES.word == "Cites"
    assert Relation.GENERALIZES.coverage is Coverage.NATIVE
    assert Relation.ADAPTS.coverage is Coverage.ADAPTED


def test_a_tool_with_no_profile_has_no_account(claims: ClaimIndex) -> None:
    """An account of a tool nobody registered would have nothing to compare a claim against."""
    with pytest.raises(ValueError, match="not a registered upstream tool"):
        _ = ToolCoverage(tool="unregistered", claims=claims).profile


def test_a_gap_falls_from_the_symbol_to_the_group_to_the_default(report: ToolCoverage) -> None:
    """Resolution runs from the specific to the general, which is what keeps the file short."""
    account = report.account

    assert account.gap(ToolRule(symbol="line-too-long", group="format")).coverage is (
        Coverage.DELEGATED
    )
    assert "formatter" in account.gap(ToolRule(symbol="bad-indentation", group="format")).reason
    assert account.gap(ToolRule(symbol="nothing", group="nowhere")) is account.default


@pytest.mark.parametrize("tool", INVENTORIED)
def test_the_frozen_inventory_is_what_the_installed_tool_ships(tool: str) -> None:
    """A frozen list nobody re-derives is a remembered figure, which is what this replaced.

    Reading Ruff's own inventory back rather than trusting a frozen same-name set once caught
    twenty-one wrong entries, so every inventory is asked of the tool itself here.
    """
    binary = {
        "ruff": "ruff",
        "clippy": "clippy-driver",
        "eslint": "eslint",
        "typescript-eslint": "eslint",
        "clang-tidy": "clang-tidy",
        "cppcheck": "cppcheck",
    }.get(tool, "")
    if binary and shutil.which(binary) is None:
        pytest.skip(f"the {tool} inventory is re-derived from {binary} itself")

    assert FrozenInventories().read(tool) == Inventory.load(tool)


def test_freezing_an_inventory_writes_the_file_the_package_ships(tmp_path: Path) -> None:
    """Regeneration is a step somebody runs rather than a memory, so it is exercised here."""
    written = FrozenInventories().write("pylint", tmp_path)

    assert written.name == "pylint.json"
    assert Inventory.model_validate_json(written.read_text()) == Inventory.load("pylint")


@pytest.mark.skipif(shutil.which("ruff") is None, reason="the delegation check runs Ruff itself")
def test_every_delegation_names_a_rule_ruff_actually_ships(report: ToolCoverage) -> None:
    """A delegation naming a code Ruff does not have is a message nobody answers.

    Ruff is asked for its own inventory rather than remembered, so a renamed or retired rule turns
    the delegation that leans on it red.
    """
    codes = {rule.code for rule in FrozenInventories().read("ruff").rules}
    cited = {
        code
        for gap in report.account.gaps
        for code in re.findall(r"(?<![-\w])[A-Z]{1,5}\d{3,4}\b", gap.reason)
    }

    assert cited
    assert cited <= codes, sorted(cited - codes)


@pytest.mark.parametrize("tool", ("ruff", "clippy"))
def test_a_tool_without_a_written_gap_falls_to_its_stated_default(
    tool: str, claims: ClaimIndex
) -> None:
    """MCMR never claimed all of Ruff, so the account says so rather than hiding it."""
    account = ToolCoverage(tool=tool, claims=claims)
    tally = account.tally()

    assert not account.account.gaps
    assert tally[Coverage.NATIVE]
    assert tally[Coverage.NATIVE] + tally[Coverage.DELEGATED] == len(account.inventory.rules)
    assert all(
        entry.reason == account.account.default.reason
        for entry in account.entries
        if not entry.rules
    )


def test_a_gap_account_reads_the_tool_it_is_named_for() -> None:
    """The data files are keyed by tool, so a report can never read another tool's gaps."""
    assert GapAccount.load("pylint").tool == "pylint"
    assert Inventory.load("clippy").tool == "clippy"
