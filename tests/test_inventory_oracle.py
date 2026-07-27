import shutil
from typing import TYPE_CHECKING

import pytest

from mcmr.inventories import (
    ClangTidyRegistry,
    CppcheckRegistry,
    ESLintRegistry,
    FrozenInventories,
    TypeScriptESLintRegistry,
)

if TYPE_CHECKING:
    from pathlib import Path

# What each tool's own program is called, so a reading of it can be skipped rather than invented.
# Pylint is left out because it answers in process, and the two ESLint registries answer from one
# Node run whose working directory is found from the ESLint binary, so both of them are present
# exactly when that binary is.
PROGRAMS = {
    "ruff": "ruff",
    "clippy": "clippy-driver",
    "eslint": "eslint",
    "typescript-eslint": "eslint",
    "clang-tidy": "clang-tidy",
    "cppcheck": "cppcheck",
}

# One capture of each listing, trimmed to the shapes the reader has to tell apart. These make the
# parsing checkable on a machine that has none of these tools installed, which is the whole reason
# the command and the reading of its answer are separate. The reading of the tool itself is checked
# below wherever the tool is present, so a capture that stopped resembling the tool cannot pass
# alone.
NODE_LISTING = """
{"eslint": {"version": "10.8.0",
  "rules": [{"symbol": "no-console", "group": "suggestion"},
            {"symbol": "no-debugger", "group": "problem"},
            {"symbol": "indent", "group": "deprecated"}]},
 "typescript-eslint": {"version": "8.65.0",
  "rules": [{"symbol": "no-explicit-any", "group": "suggestion"},
            {"symbol": "ban-types", "group": ""}]}}
"""

CLANG_TIDY_LISTING = """Enabled checks:
    bugprone-easily-swappable-parameters
    bugprone-unused-return-value

    readability-function-cognitive-complexity
    bugprone-easily-swappable-parameters
    nohyphen
"""

CLANG_TIDY_BANNER = "LLVM (http://llvm.org/):\n  LLVM version 22.1.8\n  Optimized build.\n"

CPPCHECK_LISTING = """<?xml version="1.0" encoding="UTF-8"?>
<results version="2">
    <cppcheck version="2.21.0"/>
    <errors>
        <error id="unusedFunction" severity="style" msg="never used"/>
        <error id="constStatement" severity="warning" msg="unused value"/>
        <error id="internalAstError" msg="no severity stated"/>
    </errors>
</results>
"""


@pytest.mark.parametrize("tool", sorted(PROGRAMS))
def test_every_listing_reads_the_registry_its_own_tool_prints(tool: str) -> None:
    """An inventory nobody re-derives is a remembered figure, which is what this replaced.

    Reading Ruff's own inventory back rather than trusting a frozen same-name set once caught
    twenty-one wrong entries, so every inventory is asked of the tool itself here. What is asserted
    is the contract rather than a count, since a release adds and retires rules and a case pinned
    to a number would be red on the day the tool moved rather than on the day MCMR did: the tool
    names a release, names at least one rule, and names each of them exactly once.
    """
    if shutil.which(PROGRAMS[tool]) is None:
        pytest.skip(f"the {tool} inventory is re-derived from {PROGRAMS[tool]} itself")

    inventory = FrozenInventories().read(tool)

    assert inventory.tool == tool
    assert inventory.version
    assert inventory.rules
    assert len(set(inventory.rules)) == len(inventory.rules)
    assert all(rule.symbol for rule in inventory.rules)


def test_a_captured_eslint_listing_reads_back_into_the_rules_each_package_ships() -> None:
    """One Node run answers for both registries and each reader takes the half it is for.

    A rule the package retired is grouped as deprecated rather than by its kind, since a retired
    rule is not a gap in anybody's coverage, and a rule whose metadata states no kind at all keeps
    an empty group rather than being guessed at. Both halves are named plainly, because that is the
    identity the documentation uses and the only one a reference line can spell, where a
    configuration writes the plugin half behind an `@typescript-eslint/` prefix.
    """
    core = ESLintRegistry()
    plugin = TypeScriptESLintRegistry()

    assert core.version(NODE_LISTING) == "10.8.0"
    assert plugin.version(NODE_LISTING) == "8.65.0"
    assert [(rule.symbol, rule.group) for rule in core.rules(NODE_LISTING)] == [
        ("indent", "deprecated"),
        ("no-console", "suggestion"),
        ("no-debugger", "problem"),
    ]
    assert [(rule.symbol, rule.group) for rule in plugin.rules(NODE_LISTING)] == [
        ("ban-types", ""),
        ("no-explicit-any", "suggestion"),
    ]


def test_a_captured_clang_tidy_listing_reads_back_into_the_checks_it_names() -> None:
    """The heading, the blank line, the repeat, and the name with no module are all read past."""
    registry = ClangTidyRegistry()

    assert registry.version(CLANG_TIDY_BANNER) == "22.1.8"
    assert [(rule.symbol, rule.group) for rule in registry.rules(CLANG_TIDY_LISTING)] == [
        ("bugprone-easily-swappable-parameters", "bugprone"),
        ("bugprone-unused-return-value", "bugprone"),
        ("readability-function-cognitive-complexity", "readability"),
    ]


def test_a_captured_cppcheck_listing_reads_back_into_the_identifiers_it_names() -> None:
    """The release travels with the errors, and an error stating no severity keeps none."""
    registry = CppcheckRegistry()

    assert registry.version(CPPCHECK_LISTING) == "2.21.0"
    assert [(rule.symbol, rule.group) for rule in registry.rules(CPPCHECK_LISTING)] == [
        ("constStatement", "warning"),
        ("internalAstError", ""),
        ("unusedFunction", "style"),
    ]


def test_a_listing_that_states_no_release_fails_rather_than_freezing_an_empty_one() -> None:
    """A frozen inventory with no version is one nobody tells apart from the next release."""
    with pytest.raises(ValueError, match="no LLVM version"):
        ClangTidyRegistry().version("clang-tidy said nothing about itself")
    with pytest.raises(ValueError, match="no version element"):
        CppcheckRegistry().version('<?xml version="1.0"?>\n<results version="2"/>\n')


def test_the_node_listing_runs_where_the_installed_eslint_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Node resolves a bare specifier from the directory the process runs in and nowhere else.

    So the listing is run from the project the binary on the path was installed into, walked up to
    from the script the shim points at, which is the same walk a project's own tooling does. An
    installation nothing on the path leads to fails loudly rather than answering for a registry it
    never read.
    """
    installed = tmp_path / "project" / "node_modules" / "eslint" / "bin"
    installed.mkdir(parents=True)
    (installed / "eslint.js").write_text("")
    (installed / "eslint.js").chmod(0o755)
    (tmp_path / "shims").mkdir()
    monkeypatch.setenv("PATH", str(tmp_path / "shims"))

    with pytest.raises(FileNotFoundError, match="not installed"):
        ESLintRegistry().directory()

    (tmp_path / "shims" / "eslint").symlink_to(installed / "eslint.js")
    assert ESLintRegistry().directory() == tmp_path / "project"

    (tmp_path / "loose").mkdir()
    (tmp_path / "loose" / "eslint").write_text("")
    (tmp_path / "loose" / "eslint").chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path / "loose"))
    with pytest.raises(FileNotFoundError, match="outside any node_modules"):
        ESLintRegistry().directory()
