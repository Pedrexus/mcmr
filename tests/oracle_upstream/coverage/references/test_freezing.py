import re
import shutil
from pathlib import Path

import pytest

from mcmr.accounting.inventory import FrozenInventories
from mcmr.accounting.upstream import (
    ClaimIndex,
    Coverage,
    GapAccount,
    Inventory,
    ToolCoverage,
)

from ..support import inventoried


def test_a_tool_with_no_profile_has_no_account(claims: ClaimIndex) -> None:
    """An account of a tool nobody registered would have nothing to compare a claim against."""
    with pytest.raises(ValueError, match="not a registered upstream tool"):
        _ = ToolCoverage(tool="unregistered", claims=claims).profile


def test_a_gap_falls_from_the_symbol_to_the_group_to_the_default(report: ToolCoverage) -> None:
    """Resolution runs from the specific to the general, which is what keeps the file short."""
    account = report.account

    assert account.gap(symbol="line-too-long", group="format").coverage is (Coverage.DELEGATED)
    assert "formatter" in account.gap(symbol="bad-indentation", group="format").reason
    assert account.gap(symbol="nothing", group="nowhere") is account.default


@pytest.mark.parametrize("tool", inventoried())
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

    installed = FrozenInventories().read(tool)
    frozen = Inventory.load(tool)
    if installed.version != frozen.version:
        pytest.skip(
            f"installed {tool} {installed.version} cannot verify the {frozen.version} inventory"
        )

    assert installed == frozen


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
    assert tally[Coverage.NATIVE] + tally[Coverage.DELEGATED] + tally[Coverage.ADAPTED] == len(
        account.inventory.rules
    )
    assert all(
        entry.reason == account.account.default.reason
        for entry in account.entries
        if not entry.rules
    )


def test_a_gap_account_reads_the_tool_it_is_named_for() -> None:
    """The data files are keyed by tool, so a report can never read another tool's gaps."""
    assert GapAccount.load("pylint").tool == "pylint"
    assert Inventory.load("clippy").tool == "clippy"
