from mcmr import Numeric, RulePolicies
from mcmr.domain.policy import Verdict
from mcmr.rules.general import (
    coupled_files_that_never_name_each_other,
    file_too_many_hands_have_touched,
    large_file_the_team_keeps_reopening,
)

from .support import change, coupled, history, pairs, query, record, value


def test_a_file_is_only_a_hotspot_when_it_scores_on_size_churn_and_recency() -> None:
    """Any one of the three alone names a file that costs the reader nothing."""
    busy = record("engine.py", commits=40, lines=900)
    quiet = record("generated.py", commits=1, lines=9000)
    short = record("cli.py", commits=40, lines=20)

    assert value(large_file_the_team_keeps_reopening, history(files=(busy, quiet, short))) == 1
    assert value(large_file_the_team_keeps_reopening, history(files=(quiet, short))) == 0


def test_the_hotspot_count_is_a_measurement_a_project_gives_its_own_ceiling() -> None:
    """The busiest file always reaches its own share, so a ceiling of zero is unreachable.

    Any repository whose busiest file is long and current reports at least one however carefully
    it was written, which is why the rule publishes the number and leaves the budget to whoever
    owns the tree.
    """
    files = (record("engine.py", commits=40, lines=900), record("cli.py", commits=40, lines=900))
    measured = value(large_file_the_team_keeps_reopening, history(files=files))
    owned = large_file_the_team_keeps_reopening.policy
    budgeted = RulePolicies(overrides={"ALL-HIST0001": Numeric(maximum=1)})

    assert (measured, owned) == (2, Numeric())
    assert RulePolicies().decide(measured, rule_id="ALL-HIST0001", candidate=owned) is Verdict.PASS
    assert budgeted.decide(measured, rule_id="ALL-HIST0001", candidate=owned) is Verdict.FAIL


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


def test_every_hidden_pair_names_both_files_so_a_reader_can_go_and_look() -> None:
    """A count with no pair behind it is a number nobody can act on.

    The rule used to state one aggregate finding against the history fact, located at no path at
    all, so a repository was told it had two hidden pairs and never which two.
    """
    files = (record("src/reader.py", imports=("from . import writer",)),)
    changes = (
        coupled("src/reader.py", right="src/writer.py")
        + coupled("src/codec.py", right="src/frame.py")
        + coupled("src/codec.py", right="src/wire.py")
    )
    result = query(coupled_files_that_never_name_each_other, history(files=files, changes=changes))
    assert result.findings is not None
    rows = result.findings.rows.collect().to_dicts()

    assert sorted((row["path"], row["message"]) for row in rows) == [
        (
            "src/codec.py",
            "`src/codec.py` and `src/frame.py` arrived together in 5 focused commits while "
            "neither names the other, out of the 10 and 5 each one saw",
        ),
        (
            "src/codec.py",
            "`src/codec.py` and `src/wire.py` arrived together in 5 focused commits while "
            "neither names the other, out of the 10 and 5 each one saw",
        ),
    ]
    assert [
        dict(zip(row["measurement_names"], row["measurement_values"], strict=True)) for row in rows
    ] == [
        {
            "shared commits": 5.0,
            "commits the first file saw": 10.0,
            "commits the second file saw": 5.0,
        },
        {
            "shared commits": 5.0,
            "commits the first file saw": 10.0,
            "commits the second file saw": 5.0,
        },
    ]


def test_a_repository_where_no_pair_names_any_other_reports_nothing() -> None:
    """The import reading is lexical, so total silence means it read nothing it understood."""
    changes = coupled("src/codec.py", right="src/frame.py") + coupled("src/a.py", right="src/b.py")
    coupled_rows = pairs(history(changes=changes))
    silent = query(coupled_files_that_never_name_each_other, history(changes=changes))
    assert silent.findings is not None

    assert value(coupled_files_that_never_name_each_other, history(changes=changes)) == 0
    assert coupled_rows
    assert all(pair["import_reference_count"] == 0 for pair in coupled_rows)
    assert silent.findings.rows.collect().is_empty()


def test_the_rule_owns_what_commit_width_counts_as_a_sweep() -> None:
    """The provider states width, so one project can widen policy without rebuilding facts."""
    files = (record("src/reader.py", imports=("from . import writer",)),)
    explained = coupled("src/reader.py", right="src/writer.py")
    wide = [change("src/codec.py", "src/frame.py", width=31) for _ in range(5)]
    subject = history(files=files, changes=explained + wide)

    assert wide[0].changed_file_count == 31
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
