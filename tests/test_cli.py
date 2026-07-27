from pathlib import Path

import pytest

from mcmr.catalog import Catalog
from mcmr.cli import allowance, check, coverage, floor, graph, influence
from mcmr.discovery import RuleModuleDiscovery
from mcmr.influence import InfluenceReport
from mcmr.kernel import locate
from mcmr.policy import Category, Numeric, Profile, relaxed, standard
from mcmr.upstream import ClaimIndex
from tests.test_policy import definition


def test_floor_cli_prints_the_report_without_persistence() -> None:
    floor(samples=1, facts=60)


def test_floor_cli_can_persist_the_report(tmp_path: Path) -> None:
    output = tmp_path / "floor.json"
    floor(samples=1, facts=60, output=output)
    assert '"rule_count": 277' in output.read_text()


def test_check_fails_a_repository_that_breaks_its_profile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`mcmr check` judges what it found and exits nonzero only on a failure."""
    if not locate(Path(__file__).parents[1]).exists():
        pytest.skip("the analysis kernel is not built")
    (tmp_path / "sample.py").write_text("import os\n\n\ndef load(name):\n    return name\n")

    with pytest.raises(SystemExit):
        check(tmp_path)

    output = capsys.readouterr().out
    assert "PY-IMPO0003" in output
    assert "1 files" in output


def test_check_passes_a_repository_that_meets_its_profile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Nothing to report means no failure and no exit code."""
    if not locate(Path(__file__).parents[1]).exists():
        pytest.skip("the analysis kernel is not built")
    (tmp_path / "sample.py").write_text('"""A module."""\n')

    check(tmp_path, profile="relaxed", select="imports/r0003")

    assert "0 failures" in capsys.readouterr().out


def test_the_report_states_what_each_profile_allows() -> None:
    """A failure is only readable beside the allowance it broke."""
    lines = definition("ALL-MODU0001", "int", "count")
    coverage = definition("ALL-CI0002", "float", "percentage")
    judgment = definition("ALL-ARCH0001", "category")
    accepting = Profile(
        name="own",
        categories=Category(accepted=frozenset({"cohesive"})),
        overrides={"ALL-X0001": Numeric(minimum=1, maximum=3)},
    )

    assert allowance(standard(), lines) == "<= 500"
    assert allowance(standard(), coverage) == ">= 80"
    assert allowance(accepting, judgment) == "cohesive"
    assert allowance(accepting, definition("ALL-X0001", "int")) == "1..3"
    assert allowance(relaxed(), lines) == ""
    assert allowance(relaxed(), definition("PY-IMPO0003", "bool")) == "False"


def test_graph_shows_how_declarations_reach_each_other(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The graph view names what spreads, what is file local, and what nothing reaches."""
    if not locate(Path(__file__).parents[1]).exists():
        pytest.skip("the analysis kernel is not built")
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "models.py").write_text("class User:\n    pass\n\n\ndef orphan():\n    return 1\n")
    (package / "api.py").write_text(
        "from .models import User\n\n\ndef local():\n    return 1\n\n\n"
        "def build():\n    local()\n    return User()\n"
    )

    graph(tmp_path, limit=5)

    output = capsys.readouterr().out
    assert "pkg.models.User" in output
    assert "Public but reached only by their own file" in output
    assert "Public and reached by nothing" in output


def test_coverage_cli_accounts_for_every_rule_one_tool_ships(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`mcmr coverage` prints the whole account, and narrows to one group or one state."""
    coverage()
    output = capsys.readouterr().out
    assert "MCMR against Pylint for python" in output
    assert "389 accounted for" in output

    coverage(group="classes", state="native", limit=2)
    assert "protected-access" in capsys.readouterr().out

    coverage(tool="clippy", group="perf", limit=1)
    output = capsys.readouterr().out
    assert "MCMR against Clippy for rust" in output
    assert "accounted for" in output


def test_influence_cli_names_the_works_that_shaped_the_catalog(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`mcmr influence` accounts for every reference, and narrows to one kind of source.

    The tally is asserted against the catalog rather than against a remembered number, so a rule
    gaining or losing a reference moves the test with it rather than breaking it.
    """
    catalog = Catalog(modules=RuleModuleDiscovery().modules)
    report = InfluenceReport(index=ClaimIndex(definitions=tuple(catalog.definitions)))
    references = sum(row.references for row in report.rows)

    influence()

    assert f"{references} references from 277 rules" in capsys.readouterr().out

    influence(kind="book", limit=1)
    printed = capsys.readouterr().out

    assert "book" in printed
    assert "Ruff" not in printed
