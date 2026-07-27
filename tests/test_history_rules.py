import json
import subprocess
from functools import cache
from pathlib import Path

import pytest

from mcmr.facts import CoChangedPair, FileHistory, RepositoryHistoryFact, SourceSpan
from mcmr.kernel import Kernel, locate
from mcmr.rules.general.deterministic.history.r0001 import large_file_the_team_keeps_reopening
from mcmr.rules.general.deterministic.history.r0002 import file_too_many_hands_have_touched
from mcmr.rules.general.deterministic.history.r0003 import coupled_files_that_never_name_each_other

ROOT = Path(__file__).parents[1]

# Archy is the fork this family was ported out of, so it is the oracle for both halves of it.
# `archy hotspots` ranks complexity beside churn and `archy coupling` ranks co-change, and both
# mine the same `git log` this kernel now mines.
ARCHY = ROOT.parent / "archy"


def record(
    path: str,
    *,
    commits: int = 1,
    authors: int = 1,
    days: int = 0,
    lines: int = 0,
    is_test: bool = False,
) -> FileHistory:
    """Build one file's history."""
    return FileHistory(
        path=path,
        commit_count=commits,
        author_count=authors,
        days_since_last_change=days,
        line_count=lines,
        is_test=is_test,
    )


def pair(
    left: str,
    right: str,
    *,
    shared: int = 5,
    counts: tuple[int, int] = (5, 5),
    imports: int = 0,
) -> CoChangedPair:
    """Build one pair of files that kept arriving in the same commit."""
    return CoChangedPair(
        left=left,
        right=right,
        shared_commit_count=shared,
        left_commit_count=counts[0],
        right_commit_count=counts[1],
        import_reference_count=imports,
    )


def history(
    *, files: tuple[FileHistory, ...] = (), pairs: tuple[CoChangedPair, ...] = ()
) -> RepositoryHistoryFact:
    """Build the one fact carrying everything the log said."""
    return RepositoryHistoryFact(
        key="history",
        span=SourceSpan(path=""),
        commit_count=len(files),
        files=list(files),
        pairs=list(pairs),
    )


def test_a_file_is_only_a_hotspot_when_it_scores_on_size_churn_and_recency() -> None:
    """Any one of the three alone names a file that costs the reader nothing."""
    busy = record("engine.py", commits=40, lines=900)
    quiet = record("generated.py", commits=1, lines=9000)
    short = record("cli.py", commits=40, lines=20)

    assert large_file_the_team_keeps_reopening(history(files=(busy, quiet, short))).value == 1
    assert large_file_the_team_keeps_reopening(history(files=(quiet, short))).value == 0


def test_a_file_that_stopped_changing_has_already_been_paid_for() -> None:
    """A day count runs against the newest commit, so an old window still judges its own files."""
    retired = record("legacy.py", commits=40, lines=900, days=400)

    assert large_file_the_team_keeps_reopening(history(files=(retired,))).value == 0
    assert (
        large_file_the_team_keeps_reopening(history(files=(retired,)), stale_days=500).value == 1
    )


def test_a_repository_with_no_history_at_all_concludes_nothing_from_silence() -> None:
    """Nothing to rank against means no busiest file, which is not the same as a clean tree."""
    assert large_file_the_team_keeps_reopening(history()).value == 0


def test_the_busiest_file_sets_the_bar_so_a_quiet_repository_is_judged_on_its_own_terms() -> None:
    """A share of the busiest file travels between repositories where an absolute count cannot."""
    files = (record("engine.py", commits=4, lines=900), record("cli.py", commits=8, lines=900))

    assert large_file_the_team_keeps_reopening(history(files=files)).value == 2
    assert large_file_the_team_keeps_reopening(history(files=files), busy_share=0.9).value == 1


def test_a_file_needs_both_many_hands_and_enough_commits_to_have_lost_its_owner() -> None:
    """Four people who each visited once during a rename never had an owner to lose."""
    shared = record("settings.py", commits=40, authors=9)
    renamed = record("moved.py", commits=2, authors=9)
    owned = record("codec.py", commits=40, authors=1)

    assert file_too_many_hands_have_touched(history(files=(shared, renamed, owned))) == 1
    assert file_too_many_hands_have_touched(history(files=(renamed, owned))) == 0
    assert file_too_many_hands_have_touched(history(files=(owned,)), minimum_authors=1) == 1
    assert file_too_many_hands_have_touched(history(files=(shared,)), minimum_commits=99) == 0


def test_a_coupled_pair_is_only_hidden_where_neither_file_names_the_other() -> None:
    """An import already explains the pair, and every other family here can see that one."""
    explained = pair("src/reader.py", "src/writer.py", imports=1)
    hidden = pair("src/codec.py", "src/frame.py")

    assert coupled_files_that_never_name_each_other(history(pairs=(explained, hidden))) == 1
    assert coupled_files_that_never_name_each_other(history(pairs=(explained,))) == 0


def test_a_repository_where_no_pair_names_any_other_reports_nothing() -> None:
    """The import reading is lexical, so total silence means it read nothing it understood."""
    pairs = (pair("src/codec.py", "src/frame.py"), pair("src/a.py", "src/b.py"))

    assert coupled_files_that_never_name_each_other(history(pairs=pairs)) == 0


def test_a_weakly_supported_or_thinly_confident_pair_is_left_alone() -> None:
    """Two files touched three hundred times each share five commits by accident."""
    explained = pair("src/reader.py", "src/writer.py", imports=1)
    rare = pair("src/codec.py", "src/frame.py", shared=2, counts=(2, 2))
    diluted = pair("src/codec.py", "src/log.py", shared=5, counts=(300, 300))

    assert coupled_files_that_never_name_each_other(history(pairs=(explained, rare))) == 0
    assert coupled_files_that_never_name_each_other(history(pairs=(explained, diluted))) == 0
    assert (
        coupled_files_that_never_name_each_other(
            history(pairs=(explained, rare)), minimum_shared_commits=2
        )
        == 1
    )
    assert (
        coupled_files_that_never_name_each_other(
            history(pairs=(explained, diluted)), minimum_confidence=0.01
        )
        == 1
    )


def test_a_test_changing_with_the_code_it_exercises_is_the_system_working() -> None:
    """That pair is expected, and on a test-heavy repository it buries every other one."""
    files = (record("tests/test_codec.py", is_test=True), record("src/codec.py"))
    pairs = (
        pair("src/reader.py", "src/writer.py", imports=1),
        pair("src/codec.py", "tests/test_codec.py"),
    )

    assert coupled_files_that_never_name_each_other(history(files=files, pairs=pairs)) == 0


differential = pytest.mark.skipif(
    not locate(ROOT).exists() or not ARCHY.exists(),
    reason="the differential oracle needs the kernel binary and the Archy checkout beside it",
)


@cache
def oracle(command: str) -> str:
    """Return what Archy reports for one of its two history commands, as JSON."""
    completed = subprocess.run(
        [
            "uv",
            "run",
            "--quiet",
            "--extra",
            "parser",
            "archy",
            command,
            str(ARCHY),
            "--top",
            "500",
            "--format",
            "json",
        ],
        cwd=ARCHY,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


@cache
def mined() -> RepositoryHistoryFact:
    """Return what this kernel reads from the same repository Archy is pointed at."""
    workspace = Kernel(binary=locate(ROOT), root=ARCHY).build(
        ["RepositoryHistoryFact"], {"RepositoryHistoryFact": RepositoryHistoryFact}
    )
    return workspace.stream(RepositoryHistoryFact)[0]


def relative(path: str) -> str:
    """Return one absolute path the way both readers name the same file."""
    return str(Path(path).relative_to(ARCHY))


def couple(left: str, right: str) -> tuple[str, str]:
    """Return one pair of files ordered the way both readers order it."""
    first, second = sorted((relative(left), relative(right)))
    return first, second


@differential
def test_change_counts_agree_with_archy_exactly() -> None:
    """The churn half of a hotspot is a count, so there is nothing to disagree about.

    Both readers ask `git log` for the same window and fold a rename onto the name the file
    answers to today, so every file Archy ranks has to carry the same number here. A difference
    would be a defect in one of them rather than a matter of taste.
    """
    ours = {record.path: record.commit_count for record in mined().files}
    theirs = {
        relative(row["path"]): row["churn"] for row in json.loads(oracle("hotspots"))["hotspots"]
    }

    assert theirs
    assert {path: ours.get(path) for path in theirs} == theirs


@differential
def test_the_hotspot_ranking_leads_with_the_files_archy_leads_with() -> None:
    """The head agrees exactly and the tail reorders, which is the complexity proxy differing.

    Archy weighs churn by the cyclomatic sum its own walker measured. MCMR weighs it by how long
    the file is, which is the proxy Tornhill's own hotspot maps use and the only size the history
    family carries on its own. The two rank the same worst files and then disagree about the
    middle, so equality is claimed where it is real and overlap where it is not.
    """
    ours = [
        record.path
        for record in sorted(
            mined().files, key=lambda item: (-item.line_count * item.commit_count, item.path)
        )
        if record.line_count and record.commit_count
    ]
    theirs = [relative(row["path"]) for row in json.loads(oracle("hotspots"))["hotspots"]]

    assert ours[0] == theirs[0]
    assert set(ours[:5]) == set(theirs[:5])
    assert len(set(ours[:20]) & set(theirs[:20])) >= 15


@differential
def test_the_hotspot_rule_names_the_files_archy_ranks_highest() -> None:
    """The rule turns the ranking into a count, and it has to cut where the oracle's head is."""
    subject = mined()
    busiest = max(record.commit_count for record in subject.files)
    reported = {
        record.path
        for record in subject.files
        if record.line_count >= 400
        and record.commit_count >= busiest * 0.5
        and record.days_since_last_change <= 180
    }
    theirs = [relative(row["path"]) for row in json.loads(oracle("hotspots"))["hotspots"]]

    assert large_file_the_team_keeps_reopening(subject).value == len(reported)
    assert reported == set(theirs[: len(reported)])


@differential
def test_co_change_support_and_commit_counts_agree_with_archy_exactly() -> None:
    """Every pair Archy surfaces arrives here with the same three counts behind it.

    Both readers drop a merge, drop a sweeping commit before it votes on any pair, and count the
    focused commits of each side as the base for how often one brings the other along. Those are
    the numbers a coupling claim rests on, so they are compared for equality rather than for rank.
    """
    ours = {
        (item.left, item.right): (
            item.shared_commit_count,
            sorted((item.left_commit_count, item.right_commit_count)),
        )
        for item in mined().pairs
    }
    theirs = {
        couple(row["path_a"], row["path_b"]): (
            row["support"],
            sorted((row["count_a"], row["count_b"])),
        )
        for row in json.loads(oracle("coupling"))["pairs"]
    }

    assert theirs
    assert {key: ours.get(key) for key in theirs} == theirs


@differential
def test_the_coupling_rule_reports_archys_pairs_and_explains_the_one_it_declines() -> None:
    """Every disagreement has a stated cause rather than a tolerance.

    Archy drops a pair its resolved graph connects. MCMR has no graph in this family, so it counts
    the import lines in either file that name the other and lets the rule decide. The two readings
    part on a package root. `src/archy/__init__.py` is reached by the name of its directory, so
    every module writing `from archy.cycles import ...` names it, and MCMR reads that as a stated
    dependency where Archy's graph carries no edge for it. That is a real difference in what an
    import means, so it is pinned here rather than tuned away.
    """
    subject = mined()
    tested = {record.path for record in subject.files if record.is_test}
    judged = [
        item
        for item in subject.pairs
        if not tested & {item.left, item.right}
        and item.shared_commit_count >= 5
        and item.shared_commit_count >= 0.5 * min(item.left_commit_count, item.right_commit_count)
    ]
    ours = {(item.left, item.right) for item in judged if not item.import_reference_count}
    named = {(item.left, item.right): item.import_reference_count for item in judged}
    theirs = {
        couple(row["path_a"], row["path_b"]) for row in json.loads(oracle("coupling"))["pairs"]
    }

    assert coupled_files_that_never_name_each_other(subject) == len(ours)
    assert ours <= theirs
    assert all(named.get(missing, 0) > 0 for missing in theirs - ours)
