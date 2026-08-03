from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import TypeAdapter

from mcmr.domain.contracts import RuleContract, RuleSetting, RuleValue
from mcmr.facts import FileHistory, HistoryChange, RepositoryHistoryFact, SourceSpan
from mcmr.query import RuleQuery, scalar_frame_value
from mcmr.rules.general import (
    coupled_files_that_never_name_each_other,
    file_too_many_hands_have_touched,
    large_file_the_team_keeps_reopening,
)
from mcmr.table import fact_table

if TYPE_CHECKING:
    from collections.abc import Sequence

_FIXTURES = Path(__file__).with_name("fixtures")


def value(
    rule: RuleContract,
    subject: RepositoryHistoryFact,
    **settings: RuleSetting,
) -> RuleValue:
    """Invoke one history rule once over one in-memory repository fact."""
    table = fact_table(RepositoryHistoryFact, [subject])
    query = rule.invoke_table(table, settings=settings, dependencies={})
    if not isinstance(query, RuleQuery):
        raise TypeError("a deterministic history rule returned a model query")
    return scalar_frame_value(query.values.collect())


def record(
    path: str,
    *,
    commits: int = 1,
    authors: int = 1,
    days: int = 0,
    lines: int = 0,
    is_test: bool = False,
    imports: tuple[str, ...] = (),
) -> FileHistory:
    """Build one file's history."""
    return FileHistory(
        path=path,
        author_count=authors,
        additional_commit_count=commits - authors,
        days_since_last_change=days,
        line_count=lines,
        is_test=is_test,
        imports=list(imports),
    )


def change(*paths: str, width: int | None = None) -> HistoryChange:
    """Build one commit carrying these requested paths."""
    return HistoryChange(
        other_file_count=(width or len(paths)) - len(paths),
        paths=list(paths),
    )


def coupled(
    left: str,
    *,
    right: str,
    shared: int = 5,
    counts: Sequence[int] = (5, 5),
) -> list[HistoryChange]:
    """Build commits that give one pair exact support and side counts."""
    return [
        *[change(left, right) for _ in range(shared)],
        *[change(left) for _ in range(counts[0] - shared)],
        *[change(right) for _ in range(counts[1] - shared)],
    ]


def history(
    *, files: Sequence[FileHistory] = (), changes: Sequence[HistoryChange] = ()
) -> RepositoryHistoryFact:
    """Build the one fact carrying everything the log said."""
    return RepositoryHistoryFact(
        key="history",
        span=SourceSpan(path=""),
        unscoped_commit_count=(
            max(len(changes), *(record.commit_count for record in files), 0) - len(changes)
        ),
        files=list(files),
        changes=list(changes),
    )


def test_a_file_is_only_a_hotspot_when_it_scores_on_size_churn_and_recency() -> None:
    """Any one of the three alone names a file that costs the reader nothing."""
    busy = record("engine.py", commits=40, lines=900)
    quiet = record("generated.py", commits=1, lines=9000)
    short = record("cli.py", commits=40, lines=20)

    assert value(large_file_the_team_keeps_reopening, history(files=(busy, quiet, short))) == 1
    assert value(large_file_the_team_keeps_reopening, history(files=(quiet, short))) == 0


def test_a_file_that_stopped_changing_has_already_been_paid_for() -> None:
    """A day count runs against the newest commit, so an old window still judges its own files."""
    retired = record("legacy.py", commits=40, lines=900, days=400)

    assert value(large_file_the_team_keeps_reopening, history(files=(retired,))) == 0
    assert (
        value(
            large_file_the_team_keeps_reopening,
            history(files=(retired,)),
            stale_days=500,
        )
        == 1
    )


def test_a_repository_with_no_history_at_all_concludes_nothing_from_silence() -> None:
    """Nothing to rank against means no busiest file, which is not the same as a clean tree."""
    assert value(large_file_the_team_keeps_reopening, history()) == 0


def test_one_creation_is_not_a_file_the_team_keeps_reopening() -> None:
    """A relative ranking cannot turn one initial creation into repeated change."""
    created = record("generated.py", commits=1, lines=9000)

    assert value(large_file_the_team_keeps_reopening, history(files=(created,))) == 0


def test_the_busiest_file_sets_the_bar_so_a_quiet_repository_is_judged_on_its_own_terms() -> None:
    """A share of the busiest file travels between repositories where an absolute count cannot."""
    files = (record("engine.py", commits=4, lines=900), record("cli.py", commits=8, lines=900))

    assert value(large_file_the_team_keeps_reopening, history(files=files)) == 2
    assert value(large_file_the_team_keeps_reopening, history(files=files), busy_share=0.9) == 1


def test_a_file_needs_both_many_hands_and_enough_commits_to_have_lost_its_owner() -> None:
    """Four people who each visited once during a rename never had an owner to lose."""
    shared = record("settings.py", commits=40, authors=9)
    renamed = record("moved.py", commits=4, authors=4)
    owned = record("codec.py", commits=40, authors=1)

    assert value(file_too_many_hands_have_touched, history(files=(shared, renamed, owned))) == 1
    assert value(file_too_many_hands_have_touched, history(files=(renamed, owned))) == 0
    assert (
        value(
            file_too_many_hands_have_touched,
            history(files=(owned,)),
            minimum_authors=1,
        )
        == 1
    )
    assert (
        value(
            file_too_many_hands_have_touched,
            history(files=(shared,)),
            minimum_commits=99,
        )
        == 0
    )


def test_a_coupled_pair_is_only_hidden_where_neither_file_names_the_other() -> None:
    """An import already explains the pair, and every other family here can see that one."""
    files = (record("src/reader.py", imports=("from . import writer",)),)
    explained = coupled("src/reader.py", right="src/writer.py")
    hidden = coupled("src/codec.py", right="src/frame.py")

    assert (
        value(
            coupled_files_that_never_name_each_other,
            history(files=files, changes=explained + hidden),
        )
        == 1
    )
    assert (
        value(
            coupled_files_that_never_name_each_other,
            history(files=files, changes=explained),
        )
        == 0
    )


def test_a_repository_where_no_pair_names_any_other_reports_nothing() -> None:
    """The import reading is lexical, so total silence means it read nothing it understood."""
    changes = coupled("src/codec.py", right="src/frame.py") + coupled("src/a.py", right="src/b.py")
    pairs = history(changes=changes).coupling(30)

    assert value(coupled_files_that_never_name_each_other, history(changes=changes)) == 0
    assert pairs
    assert all(pair.import_reference_count == 0 for pair in pairs)


def test_the_rule_owns_what_commit_width_counts_as_a_sweep() -> None:
    """The provider states width, so one project can widen policy without rebuilding facts."""
    files = (record("src/reader.py", imports=("from . import writer",)),)
    explained = coupled("src/reader.py", right="src/writer.py")
    wide = [change("src/codec.py", "src/frame.py", width=31) for _ in range(5)]
    subject = history(files=files, changes=explained + wide)

    assert value(coupled_files_that_never_name_each_other, subject) == 0
    assert value(coupled_files_that_never_name_each_other, subject, maximum_commit_files=31) == 1


def test_a_weakly_supported_or_thinly_confident_pair_is_left_alone() -> None:
    """Two files touched three hundred times each share five commits by accident."""
    files = (record("src/reader.py", imports=("from . import writer",)),)
    explained = coupled("src/reader.py", right="src/writer.py")
    rare = coupled("src/codec.py", right="src/frame.py", shared=2, counts=(2, 2))
    diluted = coupled("src/codec.py", right="src/log.py", shared=5, counts=(300, 300))

    assert (
        value(
            coupled_files_that_never_name_each_other,
            history(files=files, changes=explained + rare),
        )
        == 0
    )
    assert (
        value(
            coupled_files_that_never_name_each_other,
            history(files=files, changes=explained + diluted),
        )
        == 0
    )
    assert (
        value(
            coupled_files_that_never_name_each_other,
            history(files=files, changes=explained + rare),
            minimum_shared_commits=2,
        )
        == 1
    )
    assert (
        value(
            coupled_files_that_never_name_each_other,
            history(files=files, changes=explained + diluted),
            minimum_confidence=0.01,
        )
        == 1
    )


def test_a_test_changing_with_the_code_it_exercises_is_the_system_working() -> None:
    """That pair is expected, and on a test-heavy repository it buries every other one."""
    files = (
        record("tests/test_codec.py", is_test=True),
        record("src/reader.py", imports=("from . import writer",)),
    )
    changes = coupled("src/reader.py", right="src/writer.py") + coupled(
        "src/codec.py", right="tests/test_codec.py"
    )

    assert (
        value(
            coupled_files_that_never_name_each_other,
            history(files=files, changes=changes),
        )
        == 0
    )


@cache
def hotspots() -> list[tuple[str, int]]:
    """Read the Archy hotspot result frozen at commit `408679b`."""
    return TypeAdapter(list[tuple[str, int]]).validate_json(
        (_FIXTURES / "archy-408679b-hotspots.json").read_text()
    )


@cache
def mined() -> RepositoryHistoryFact:
    """Read the MCMR history fact frozen beside the independent oracle result."""
    return RepositoryHistoryFact.model_validate_json(
        (_FIXTURES / "archy-408679b-history.json").read_text()
    )


@cache
def coupling() -> list[tuple[str, str, int, int, int]]:
    """Read the Archy coupling result frozen at commit `408679b`."""
    return TypeAdapter(list[tuple[str, str, int, int, int]]).validate_json(
        (_FIXTURES / "archy-408679b-coupling.json").read_text()
    )


def test_change_counts_agree_with_archy_exactly() -> None:
    """The churn half of a hotspot is a count, so there is nothing to disagree about.

    Both readers ask `git log` for the same window and fold a rename onto the name the file
    answers to today, so every file Archy ranks has to carry the same number here. A difference
    would be a defect in one of them rather than a matter of taste.
    """
    ours = {record.path: record.commit_count for record in mined().files}
    theirs = dict(hotspots())

    assert theirs
    assert {path: ours.get(path) for path in theirs} == theirs


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
    theirs = [path for path, _ in hotspots()]

    assert ours[0] == theirs[0]
    assert set(ours[:5]) == set(theirs[:5])
    assert len(set(ours[:20]) & set(theirs[:20])) >= 15


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
    theirs = [path for path, _ in hotspots()]

    assert value(large_file_the_team_keeps_reopening, subject) == len(reported)
    assert reported == set(theirs[: len(reported)])


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
        for item in mined().coupling(30)
    }
    theirs = {
        ((left, right) if left <= right else (right, left)): (
            support,
            sorted((left_count, right_count)),
        )
        for left, right, support, left_count, right_count in coupling()
    }

    assert theirs
    assert {key: ours.get(key) for key in theirs} == theirs


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
    pairs = subject.coupling(30)
    tested = {record.path for record in subject.files if record.is_test}
    judged = [
        item
        for item in pairs
        if not tested & {item.left, item.right}
        and item.shared_commit_count >= 5
        and item.shared_commit_count >= 0.5 * min(item.left_commit_count, item.right_commit_count)
    ]
    ours = {(item.left, item.right) for item in judged if not item.import_reference_count}
    named = {(item.left, item.right): item.import_reference_count for item in judged}
    theirs = {(left, right) if left <= right else (right, left) for left, right, *_ in coupling()}

    assert value(coupled_files_that_never_name_each_other, subject) == len(ours)
    assert ours <= theirs
    assert all(named.get(missing, 0) > 0 for missing in theirs - ours)
