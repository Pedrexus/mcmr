import json
import subprocess
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from mcmr.cli import diff as diff_command
from mcmr.cli import snapshot as snapshot_command
from mcmr.cli import trend as trend_command
from mcmr.comparisons import (
    ComparisonText,
    Incomparable,
    ReportFormat,
    RuleChange,
    RunComparison,
    RunSeries,
    SeriesText,
    change,
    excess,
)
from mcmr.policy import Boolean, Category, Numeric
from mcmr.projections import JsonRendering
from mcmr.runs import FailingSite, RuleRecord, RunIdentity, RunRecord, RunStats, RunStore
from tests.conftest import BINARY, needs_kernel
from tests.test_runs import repository

if TYPE_CHECKING:
    from pathlib import Path


def rule(
    identifier: str,
    *failing: tuple[str, int],
    contract: str = "0000000000000000",
    maximum: float | None = 0,
) -> RuleRecord:
    """Build one rule record failing at the named sites, under a ceiling by default."""
    return RuleRecord(
        rule=identifier,
        contract=contract,
        policy=Numeric(maximum=maximum),
        observations=6,
        unassessed=1,
        failing=tuple(FailingSite(fact=site, value=value) for site, value in failing),
    )


def run(
    *rules: RuleRecord,
    profile: str = "standard",
    when: str = "2026-07-26T00:00:00Z",
    commit: str = "aaaaaaa",
) -> RunRecord:
    """Build one run record over the rules a test cares about."""
    return RunRecord(
        profile=profile,
        identity=RunIdentity(taken_at=when, commit=commit, branch="main"),
        stats=RunStats(file_count=4, fact_count=20, invocation_count=40),
        rules=rules,
    )


def test_a_diff_names_what_arrived_what_went_and_what_grew_where_it_stood() -> None:
    """Four things can happen to a finding, and a report that folded them would hide three."""
    baseline = run(
        rule("ALL-A0001", ("kept.py", 3), ("gone.py", 1)),
        rule("ALL-B0001", ("eased.py", 9)),
    )
    current = run(
        rule("ALL-A0001", ("kept.py", 7), ("new.py", 2)),
        rule("ALL-B0001", ("eased.py", 4)),
    )

    comparison = RunComparison.between(baseline, current)

    assert comparison.before == 3
    assert comparison.after == 3
    assert [item.rule for item in comparison.regressed] == ["ALL-A0001"]
    assert [item.rule for item in comparison.improved] == ["ALL-B0001"]
    assert comparison.shifted == ()
    regressed = comparison.regressed[0]
    assert [item.fact for item in regressed.appeared] == ["new.py"]
    assert [item.fact for item in regressed.resolved] == ["gone.py"]
    assert [(item.before, item.after) for item in regressed.worsened] == [(3, 7)]
    assert regressed.drift == 1
    assert comparison.improved[0].eased[0].fact == "eased.py"


def test_a_finding_that_only_moved_is_neither_a_regression_nor_an_improvement() -> None:
    """A report calling a relocated finding progress would be wrong twice over."""
    baseline = run(rule("ALL-A0001", ("here.py", 2)))
    current = run(rule("ALL-A0001", ("there.py", 2)))

    comparison = RunComparison.between(baseline, current)

    assert comparison.regressed == ()
    assert comparison.improved == ()
    assert [item.rule for item in comparison.shifted] == ["ALL-A0001"]
    assert comparison.shifted[0].drift == 0


def test_a_rule_that_did_not_move_is_left_out_of_every_list() -> None:
    """A diff that listed every unchanged rule would bury the ones that moved."""
    baseline = run(rule("ALL-A0001", ("same.py", 2)))

    comparison = RunComparison.between(baseline, baseline)

    assert (comparison.regressed, comparison.improved, comparison.shifted) == ((), (), ())
    assert comparison.catalog_moved is False


def test_two_runs_judged_under_different_profiles_are_refused_rather_than_subtracted() -> None:
    """Two verdicts stating different intentions have no difference worth reporting."""
    baseline = run(rule("ALL-A0001"), profile="relaxed")
    current = run(rule("ALL-A0001"))

    with pytest.raises(Incomparable, match="relaxed"):
        RunComparison.between(baseline, current)


def test_a_rule_the_baseline_never_held_is_newly_judged_rather_than_a_regression() -> None:
    """A rule added after a baseline was taken cannot have regressed against it."""
    baseline = run(rule("ALL-A0001", ("a.py", 1)))
    current = run(rule("ALL-A0001", ("a.py", 1)), rule("ALL-NEW0001", ("b.py", 4), ("c.py", 5)))

    comparison = RunComparison.between(baseline, current)

    assert comparison.regressed == ()
    assert [item.rule for item in comparison.introduced] == ["ALL-NEW0001"]
    assert comparison.before == comparison.after == 1
    assert comparison.catalog_moved is True


def test_a_rule_the_catalog_dropped_is_retired_rather_than_an_improvement() -> None:
    """Deleting a rule is not the same as fixing the code it used to report."""
    baseline = run(rule("ALL-A0001", ("a.py", 1)), rule("ALL-OLD0001", ("b.py", 9)))
    current = run(rule("ALL-A0001", ("a.py", 1)))

    comparison = RunComparison.between(baseline, current)

    assert comparison.improved == ()
    assert [item.rule for item in comparison.retired] == ["ALL-OLD0001"]
    assert comparison.before == comparison.after == 1


def test_a_rule_whose_contract_or_whose_bar_moved_is_named_rather_than_compared() -> None:
    """A rule measuring something else, or held to a new bar, is not the rule that was recorded."""
    baseline = run(rule("ALL-A0001", ("a.py", 4)), rule("ALL-B0001", ("b.py", 4)))
    current = run(
        rule("ALL-A0001", ("a.py", 4), ("second.py", 9), contract="ffffffffffffffff"),
        rule("ALL-B0001", ("b.py", 4), ("third.py", 9), maximum=8),
    )

    comparison = RunComparison.between(baseline, current)

    assert comparison.regressed == ()
    assert comparison.redefined == ("ALL-A0001", "ALL-B0001")
    assert comparison.before == comparison.after == 0


def test_a_magnitude_is_read_against_the_bar_the_profile_actually_stated() -> None:
    """A value falls outside a floor by being small and outside a ceiling by being large."""
    assert excess(Numeric(maximum=0), 4) == 4
    assert excess(Numeric(minimum=80.0), 60.0) == 20.0
    assert excess(Numeric(minimum=1, maximum=3), 2) == 0
    assert excess(Numeric(minimum=1, maximum=3), 9) == 6
    assert excess(Boolean(), True) == 0.0
    assert excess(Category(accepted=frozenset({"a"})), "b") == 0.0
    assert excess(None, 4) == 0.0


def test_a_value_carrying_no_magnitude_reports_only_that_a_site_failed() -> None:
    """One rejected category is not further from acceptable than another."""
    categorical = RuleRecord(
        rule="ALL-C0001",
        contract="1111111111111111",
        policy=Category(accepted=frozenset({"cohesive"})),
        failing=(FailingSite(fact="pkg", value="tangled"),),
    )
    other = categorical.model_copy(
        update={"failing": (FailingSite(fact="pkg", value="scattered"),)}
    )

    moved = change(categorical, other)

    assert moved.worsened == ()
    assert moved.eased == ()
    assert moved.moved is False


def test_a_series_holds_one_profile_and_says_how_each_run_moved_from_the_one_before() -> None:
    """A line drawn through two profiles would be a line through two different questions."""
    records = [
        run(rule("ALL-A0001", ("a.py", 1)), when="2026-07-20T00:00:00Z", commit="1111111"),
        run(rule("ALL-A0001"), when="2026-07-21T00:00:00Z", commit="2222222"),
        run(
            rule("ALL-A0001", ("a.py", 1)),
            rule("ALL-NEW0001", ("b.py", 3)),
            when="2026-07-22T00:00:00Z",
            commit="3333333",
        ),
        run(rule("ALL-A0001"), profile="strict", when="2026-07-23T00:00:00Z"),
    ]

    series = RunSeries.of(records, "standard")

    assert series.recorded == 3
    assert [point.drift for point in series.points] == [None, -1, 1]
    assert [point.catalog_moved for point in series.points] == [False, False, True]
    assert [point.failing for point in series.points] == [1, 0, 2]
    assert [point.failing_rules for point in series.points] == [1, 0, 2]
    assert series.points[0].unassessed == 1
    assert RunSeries.of(records, "standard", 2).points == series.points[1:]
    assert RunSeries.of(records, "relaxed").points == ()


def test_the_comparison_text_states_the_direction_and_names_every_list() -> None:
    """A reader wants the direction first and then the rules that produced it."""
    baseline = run(rule("ALL-A0001", ("a.py", 1)), rule("ALL-OLD0001"))
    current = run(
        rule("ALL-A0001", ("a.py", 1), ("b.py", 2)),
        rule("ALL-NEW0001", ("c.py", 3)),
        commit="bbbbbbb",
    )

    rendered = ComparisonText().render(RunComparison.between(baseline, current))

    assert "MCMR run comparison under the standard profile" in rendered
    assert "from aaaaaaa at 2026-07-26T00:00:00Z to bbbbbbb at 2026-07-26T00:00:00Z" in rendered
    assert (
        "1 failing sites became 2 (+1) across the rules both runs judged the same way" in rendered
    )
    assert "1 rules newly judged, 1 retired, 0 redefined" in rendered
    assert "Regressed (1)\n  ALL-A0001 +1 allowed <= 0" in rendered
    assert "Newly judged (1)\n  ALL-NEW0001 1 failing, allowed <= 0" in rendered
    assert "Retired (1)\n  ALL-OLD0001 0 failing, allowed <= 0" in rendered
    assert "Redefined (0)" in rendered


def test_the_comparison_text_bounds_every_list_it_prints() -> None:
    """A diff of a large repository is unreadable unless it states its own truncation."""
    baseline = run(rule("ALL-A0001"), rule("ALL-B0001"), rule("ALL-C0001"))
    current = run(
        rule("ALL-A0001", ("a.py", 1)),
        rule("ALL-B0001", ("b.py", 1)),
        rule("ALL-C0001", ("c.py", 1)),
    )

    rendered = ComparisonText(limit=2).render(RunComparison.between(baseline, current))

    assert "Regressed (3)" in rendered
    assert "  and 1 more" in rendered


def test_a_rule_change_says_in_one_line_what_happened_to_it() -> None:
    """A rule with no bar at all still reports the shape of its own movement."""
    empty = RuleChange(rule="ALL-A0001", appeared=(FailingSite(fact="a.py", value=1),))

    assert empty.summary() == (
        "ALL-A0001 +1 allowed nothing stated, 1 appeared, 0 resolved, 0 worse, 0 easier"
    )


def test_the_series_text_says_nothing_about_a_direction_it_cannot_state() -> None:
    """The first run followed nothing, and a catalog that moved explains a jump in the totals."""
    records = [
        run(rule("ALL-A0001"), when="2026-07-20T00:00:00Z", commit="1111111"),
        run(
            rule("ALL-A0001", ("a.py", 1)),
            rule("ALL-NEW0001"),
            when="2026-07-21T00:00:00Z",
            commit="2222222",
        ),
    ]

    rendered = SeriesText().render(RunSeries.of(records, "standard"))

    assert "MCMR trend over 2 of 2 runs recorded under the standard profile" in rendered
    assert "when                     commit" in rendered
    assert "2026-07-20T00:00:00Z     1111111" in rendered
    assert "  first" in rendered
    assert " same" in rendered
    assert "     +1" in rendered
    assert " moved" in rendered


def test_the_format_chooses_the_rendering_for_either_report() -> None:
    """A new format is a member and a class of its own, never a change to the comparison."""
    comparison = RunComparison.between(run(rule("ALL-A0001")), run(rule("ALL-A0001")))
    series = RunSeries.of([run(rule("ALL-A0001"))], "standard")

    assert isinstance(ReportFormat.TEXT.comparison(5), ComparisonText)
    assert isinstance(ReportFormat.JSON.comparison(5), JsonRendering)
    assert isinstance(ReportFormat.TEXT.series(), SeriesText)
    assert isinstance(ReportFormat.JSON.series(), JsonRendering)
    assert json.loads(ReportFormat.JSON.comparison(5).render(comparison))["profile"] == "standard"
    assert json.loads(ReportFormat.JSON.series().render(series))["recorded"] == 1


def test_two_comparisons_of_the_same_two_runs_render_the_same_bytes() -> None:
    """A report a reader diffs across commits has to be identical when nothing moved."""
    baseline = run(rule("ALL-A0001", ("a.py", 1)), rule("ALL-OLD0001"))
    current = run(rule("ALL-A0001", ("b.py", 2)), rule("ALL-NEW0001", ("c.py", 3)))
    runs = [RunComparison.between(baseline, current) for _ in range(2)]

    assert ComparisonText().render(runs[0]) == ComparisonText().render(runs[1])
    assert JsonRendering().render(runs[0]) == JsonRendering().render(runs[1])


@needs_kernel
def test_the_diff_command_holds_a_repository_against_the_run_it_recorded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`mcmr diff` is the gate a project puts between one commit and the next."""
    root = repository(tmp_path / "checkout")
    snapshot_command(root, kernel=BINARY, select="imports.r0003")
    capsys.readouterr()

    diff_command(root, kernel=BINARY, select="imports.r0003")
    assert "0 failing sites became 0 (+0)" in capsys.readouterr().out

    (root / "pkg" / "engine.py").write_text(
        '"""Engine."""\n\nimport json\n\nfrom .store import load\n\n\n'
        'def run():\n    """Run."""\n    return load()\n'
    )
    with pytest.raises(SystemExit) as regression:
        diff_command(root, kernel=BINARY, select="imports.r0003")

    assert regression.value.code == 1
    assert "Regressed (1)\n  PY-IMPO0003 +1" in capsys.readouterr().out


@needs_kernel
def test_the_diff_command_compares_two_recorded_runs_without_judging_again(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two runs already on disk are two runs, so a comparison of them needs no third."""
    root = repository(tmp_path / "checkout")
    snapshot_command(root, kernel=BINARY, select="imports.r0003", output=tmp_path / "before.json")
    snapshot_command(root, kernel=BINARY, select="imports.r0003", output=tmp_path / "after.json")
    capsys.readouterr()

    diff_command(
        root,
        baseline=tmp_path / "before.json",
        current=tmp_path / "after.json",
        format=ReportFormat.JSON,
    )

    written = json.loads(capsys.readouterr().out)
    assert written["regressed"] == []
    assert written["profile"] == "standard"


def test_the_diff_command_says_so_when_nothing_was_ever_recorded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing baseline is a thing to be told about, not a comparison against nothing."""
    with pytest.raises(SystemExit) as missing:
        diff_command(tmp_path)

    assert missing.value.code == 2
    assert "so run `mcmr snapshot" in capsys.readouterr().out


def test_the_diff_command_refuses_two_runs_judged_under_different_profiles(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The refusal reaches the reader as a sentence rather than as a traceback."""
    store = RunStore(directory=tmp_path)
    baseline = store.write(run(rule("ALL-A0001"), profile="relaxed"))
    current = store.write(run(rule("ALL-A0001"), when="2026-07-27T00:00:00Z"))

    with pytest.raises(SystemExit) as refusal:
        diff_command(tmp_path, baseline=baseline, current=current)

    assert refusal.value.code == 2
    assert "state different intentions" in capsys.readouterr().out


def test_the_trend_command_reads_the_store_a_repository_already_holds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`mcmr trend` is the view over everything a project recorded about itself."""
    store = RunStore(directory=tmp_path / ".mcmr")
    store.write(run(rule("ALL-A0001"), when="2026-07-20T00:00:00Z", commit="1111111"))
    store.write(run(rule("ALL-A0001", ("a.py", 1)), when="2026-07-21T00:00:00Z", commit="2222222"))

    trend_command(tmp_path)
    assert "MCMR trend over 2 of 2 runs" in capsys.readouterr().out

    trend_command(tmp_path, format=ReportFormat.JSON, last=1)
    written = json.loads(capsys.readouterr().out)
    assert [point["identity"]["commit"] for point in written["points"]] == ["2222222"]


@needs_kernel
def test_a_repository_moving_across_real_commits_reads_as_a_direction(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The whole point is answering whether a codebase got better, over its own history."""
    root = repository(tmp_path / "checkout")
    snapshot_command(root, kernel=BINARY, select="imports.r0003")
    (root / "pkg" / "engine.py").write_text(
        '"""Engine."""\n\nimport json\n\nfrom .store import load\n\n\n'
        'def run():\n    """Run."""\n    return load()\n'
    )
    commit(root, "second")
    snapshot_command(root, kernel=BINARY, select="imports.r0003")
    (root / "pkg" / "engine.py").write_text(
        '"""Engine."""\n\nfrom .store import load\n\n\n'
        'def run():\n    """Run."""\n    return load()\n'
    )
    commit(root, "third")
    snapshot_command(root, kernel=BINARY, select="imports.r0003")
    capsys.readouterr()

    trend_command(root, format=ReportFormat.JSON)

    written = json.loads(capsys.readouterr().out)
    assert [point["drift"] for point in written["points"]] == [None, 1, -1]
    assert [point["failing"] for point in written["points"]] == [0, 1, 0]
    assert len({point["identity"]["commit"] for point in written["points"]}) == 3
    assert all(point["catalog_moved"] is False for point in written["points"][1:])


def commit(root: Path, message: str) -> None:
    """Record everything the tree holds as one commit."""
    for arguments in (("add", "-A"), ("commit", "-qm", message)):
        subprocess.run(["git", "-C", str(root), *arguments], check=True, capture_output=True)


@needs_kernel
def test_a_snapshot_written_now_is_the_baseline_the_next_run_is_held_to(tmp_path: Path) -> None:
    """The store and the comparison are one loop, so the whole path is exercised as one."""
    root = repository(tmp_path / "checkout")
    snapshot_command(root, kernel=BINARY, select="imports.r0003")
    store = RunStore(directory=root / ".mcmr")
    baseline = store.latest("standard")

    assert baseline is not None
    assert baseline.identity.taken_at.endswith("Z")
    assert datetime.fromisoformat(baseline.identity.taken_at) <= datetime.now(UTC)
    assert RunComparison.between(baseline, baseline).regressed == ()
