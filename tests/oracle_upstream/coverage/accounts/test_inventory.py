from typing import TYPE_CHECKING

import pytest

from mcmr.accounting.upstream import (
    ClaimIndex,
    Coverage,
    GapAccount,
    Inventory,
    ToolCoverage,
    ToolRegistry,
    ToolRule,
)
from mcmr.domain.contracts import RuleDefinition, RuleScope

from ..support import inventoried, inventory_sizes

if TYPE_CHECKING:
    from collections.abc import Sequence


def test_every_rule_the_inventory_holds_is_accounted_for(report: ToolCoverage) -> None:
    """A tool claiming to supersede another owes an entry for every rule it emits."""
    assert len(report.entries) == len(report.inventory.rules)
    assert len(report.inventory.rules) == 389
    assert {entry.rule.code for entry in report.entries} == {
        rule.code for rule in report.inventory.rules
    }


@pytest.mark.parametrize("tool", inventoried())
def test_every_registered_inventory_has_an_account(tool: str, claims: ClaimIndex) -> None:
    """Every frozen registry loads beside a written answer for each rule it ships."""
    report = ToolCoverage(tool=tool, claims=claims)

    assert set(inventoried()) == set(inventory_sizes())
    assert len(report.inventory.rules) == inventory_sizes()[tool]
    assert len(report.entries) == inventory_sizes()[tool]
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
    definitions: Sequence[RuleDefinition], claims: ClaimIndex
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
        (upstream.symbol, claim.rule)
        for claim in claims.claims
        if (upstream := claim.upstream) is not None
        if upstream.tool == "Pylint" and by_id[claim.rule].scope not in answerable
    }

    assert not wrong, sorted(wrong)


def test_every_claim_covers_the_language_boundary_of_its_tool(claims: ClaimIndex) -> None:
    """A language-specific rule cannot answer an inventory spanning another language."""
    registry = ToolRegistry()
    wrong = {
        (upstream.tool, claim.rule, claim.scope)
        for claim in claims.claims
        if (upstream := claim.upstream) is not None
        if not claim.covers(registry.by_name[upstream.tool.casefold()])
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
        if claims.of(tool="Pylint", code=rule.code, symbol=rule.symbol)
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


@pytest.mark.parametrize("tool", inventoried())
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
    assert all(gap == clang.gaps[0] for gap in clang.by_group.values())
    assert GapAccount.load("cppcheck").by_group["information"].coverage is Coverage.INAPPLICABLE
