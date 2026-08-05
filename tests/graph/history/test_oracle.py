from mcmr.rules.general import (
    coupled_files_that_never_name_each_other,
    large_file_the_team_keeps_reopening,
)

from .support import coupling, hotspots, mined, pairs, value


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
        (str(item["left"]), str(item["right"])): (
            item["shared_commit_count"],
            sorted((item["left_commit_count"], item["right_commit_count"])),
        )
        for item in pairs(mined())
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
    coupled = pairs(subject)
    tested = {record.path for record in subject.files if record.is_test}
    judged = [
        item
        for item in coupled
        if not tested & {str(item["left"]), str(item["right"])}
        and item["shared_commit_count"] >= 5
        and item["shared_commit_count"]
        >= 0.5 * min(item["left_commit_count"], item["right_commit_count"])
    ]
    ours = {
        (str(item["left"]), str(item["right"]))
        for item in judged
        if not item["import_reference_count"]
    }
    named = {
        (str(item["left"]), str(item["right"])): item["import_reference_count"] for item in judged
    }
    theirs = {(left, right) if left <= right else (right, left) for left, right, *_ in coupling()}

    assert value(coupled_files_that_never_name_each_other, subject) == len(ours)
    assert ours <= theirs
    assert all(named.get(missing, 0) > 0 for missing in theirs - ours)
