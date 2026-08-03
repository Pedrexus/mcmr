from pathlib import Path

import pytest

from mcmr import (
    Category,
    Numeric,
    RulePolicies,
)
from mcmr.accounting.upstream import ClaimIndex
from mcmr.audit.influence import InfluenceReport
from mcmr.commands.insight import coverage, graph, influence
from mcmr.commands.interface import RepairMode
from mcmr.commands.quality import (
    allowance,
    check,
)
from mcmr.kernel import locate
from mcmr.rulebook.catalog import Catalog
from mcmr.rulebook.discovery import RuleModuleDiscovery

from ..test_policy import definition

_PACKAGE = Path(__file__).parents[3]


def rendered_coverage(
    capsys: pytest.CaptureFixture[str],
    *,
    tool: str = "all",
    group: str = "",
    state: str = "",
    limit: int = 0,
) -> str:
    """Run one coverage view and return only what that invocation rendered."""
    coverage(tool=tool, group=group, state=state, limit=limit)
    return capsys.readouterr().out


def test_check_applies_only_a_safe_fix_that_its_rule_verifies(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The write survives only after a fresh run proves the originating finding closed."""
    if not locate(_PACKAGE).exists():
        pytest.skip("the analysis kernel is not built")
    module = tmp_path / "sample.py"
    module.write_text(
        '''"""A module."""

def ready(value: str | None) -> bool:
    return bool(value is None)
'''
    )

    check(tmp_path, select="PY-TYPE0008", repair=RepairMode.APPLY)

    output = capsys.readouterr().out
    assert "applied" in output
    assert "rule verified" in output
    assert "0 failures" in output
    assert module.read_text() == (
        '"""A module."""\n\ndef ready(value: str | None) -> bool:\n    return value is None\n'
    )


def test_check_applies_a_review_fix_only_when_explicitly_requested(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Review plans use the same verified fixpoint behind an explicit repair mode."""
    if not locate(_PACKAGE).exists():
        pytest.skip("the analysis kernel is not built")
    module = tmp_path / "sample.py"
    module.write_text(
        """class Receipt:
    def save(self) -> None:
        pass

    def open(self) -> None:
        pass
"""
    )

    check(tmp_path, select="ALL-CLAS0001", repair=RepairMode.APPLY_REVIEW)

    output = capsys.readouterr().out
    assert "applied" in output
    assert "rule verified" in output
    assert "0 failures" in output
    assert module.read_text() == (
        """class Receipt:
    def open(self) -> None:
        pass

    def save(self) -> None:
        pass
"""
    )


def test_the_report_states_what_each_rule_policy_allows() -> None:
    """A failure is only readable beside the allowance it broke."""
    lines = definition("ALL-MODU0001", output="int", unit="count", policy=Numeric(maximum=500))
    coverage = definition(
        "ALL-CI0002", output="float", unit="percentage", policy=Numeric(minimum=80)
    )
    judgment = definition("ALL-ARCH0001", output="category")
    accepting = RulePolicies(
        overrides={
            judgment.id: Category(good={"cohesive"}),
            "ALL-X0001": Numeric(minimum=1, maximum=3),
        },
    )

    assert allowance(RulePolicies(), lines) == "<= 500"
    assert allowance(RulePolicies(), coverage) == ">= 80"
    assert allowance(accepting, judgment) == "good cohesive"
    assert allowance(accepting, definition("ALL-X0001", output="int")) == "1..3"
    assert allowance(RulePolicies(), definition("PY-IMPO0003", output="bool")) == "False"


def test_graph_shows_how_declarations_reach_each_other(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The graph view names what spreads, what is file local, and what nothing reaches."""
    if not locate(_PACKAGE).exists():
        pytest.skip("the analysis kernel is not built")
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "models.py").write_text("class User:\n    pass\n\n\ndef orphan():\n    return 1\n")
    (package / "api.py").write_text(
        """from .models import User


def local():
    return 1


def build():
    local()
    return User()
"""
    )

    graph(tmp_path, limit=5)

    output = capsys.readouterr().out
    assert all(
        expected in output
        for expected in (
            "pkg.models.User",
            "Public but reached only by their own file",
            "Public and reached by nothing",
        )
    )


def test_coverage_cli_accounts_for_every_rule_one_tool_ships(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`mcmr coverage` summarizes every account and can open one tool in detail."""
    output = rendered_coverage(capsys)
    assert all(
        expected in output
        for expected in (
            "MCMR coverage across 7 upstream tools",
            "Pylint",
            "cppcheck",
            "3,538 upstream rules accounted for",
        )
    )

    output = rendered_coverage(capsys, tool="pylint")
    for expected in ("MCMR against Pylint for python", "389 accounted for"):
        assert expected in output

    assert "protected-access" in rendered_coverage(
        capsys, tool="pylint", group="classes", state="native", limit=2
    )

    output = rendered_coverage(capsys, tool="clippy", group="perf", limit=1)
    for expected in ("MCMR against Clippy for rust", "accounted for"):
        assert expected in output


def test_influence_cli_names_the_works_that_shaped_the_catalog(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`mcmr influence` accounts for every reference, and narrows to one kind of source.

    The tally is asserted against the catalog rather than against a remembered number, so a rule
    gaining or losing a reference moves the test with it rather than breaking it.
    """
    catalog = Catalog(modules=RuleModuleDiscovery().modules)
    report = InfluenceReport(index=ClaimIndex(definitions=list(catalog.definitions)))
    references = sum(row.references for row in report.rows)

    influence()

    assert f"{references} references from 275 rules" in capsys.readouterr().out

    influence(kind="book", limit=1)
    printed = capsys.readouterr().out

    assert "book" in printed
    assert "Ruff" not in printed
