from typing import TYPE_CHECKING

import pytest
from hypothesis import given
from hypothesis import strategies as st

from mcmr.facts import ModuleFact
from tests.oracle import (
    Comparison,
    DeclarationReader,
    Oracle,
    Reader,
    Relation,
    Report,
    Shape,
    Site,
    Trees,
    assembled,
    differ,
    written,
)

if TYPE_CHECKING:
    from pathlib import Path

DECLARATION = Site(path="app.py", line=1, through=9)
INSIDE = Site.at("app.py", 4)
ELSEWHERE = Site.at("other.py", 4)


def stated(name: str, *sites: Site) -> Report:
    """Return one reader's answer, written out."""
    return Report(reader=name, sites=sites)


def test_both_halves_of_a_comparison_satisfy_the_same_reader() -> None:
    """A tool adapter and a rule reader are interchangeable, which is what makes one relation work.

    Neither side of a comparison learns what the other is, so a new tool is one adapter and a new
    way of locating a rule's findings is one reader, and no comparison changes to admit either.
    """
    readers: tuple[Reader, ...] = (
        Oracle.of("ruff", "F401"),
        DeclarationReader(rule_id="PY-IMPO0003", family=ModuleFact),
    )

    assert [reader.name for reader in readers] == ["ruff F401", "PY-IMPO0003"]
    assert all(callable(reader.report) for reader in readers)


def test_a_finding_is_located_by_the_path_relative_to_the_tree_and_not_by_a_name() -> None:
    """Two files of the same name in one tree are two places, which a base name cannot say.

    An oracle comparison once asserted that the two readers named the same files and passed on a
    one-file fixture whatever either of them answered, so nothing here can be built from a name.
    """
    assert Site.at("pkg/__init__.py", 1) != Site.at("other/__init__.py", 1)
    assert DECLARATION.holds(INSIDE)
    assert not DECLARATION.holds(ELSEWHERE)
    assert DECLARATION.width == 9
    assert INSIDE.width == 1


def test_a_report_counts_two_findings_on_one_line_as_two() -> None:
    """A multiset rather than a set, since a reader that found one of them has not agreed."""
    twice = stated("ours", INSIDE, INSIDE)

    assert twice.states(INSIDE, INSIDE)
    assert not twice.states(INSIDE)
    assert not Comparison(
        ours=twice, theirs=(stated("theirs", INSIDE),), relation=Relation.EQUALS, reason="two"
    ).holds()


def test_a_line_pinned_reader_is_folded_into_the_declaration_a_rule_answered_for() -> None:
    """Each reader pins a finding as precisely as its evidence allows, so one has to move.

    The finer side is expressed in the coarser side's ranges, which is what lets a rule reading a
    whole callable be compared against a tool naming a line inside it, and a finding in some other
    file stays exactly where it is so the disagreement is visible.
    """
    ours = stated("ours", DECLARATION)
    theirs = stated("theirs", INSIDE)

    differ(ours, Relation.EQUALS, theirs, because="the line sits inside the declaration")
    assert not Comparison(
        ours=ours,
        theirs=(stated("theirs", ELSEWHERE),),
        relation=Relation.EQUALS,
        reason="elsewhere",
    ).holds()


def test_the_narrowest_range_holding_a_line_is_the_one_it_folds_into() -> None:
    """A finding in the wrong method fails even where the class around it holds them both."""
    method = Site(path="app.py", line=6, through=8)
    other = Site(path="app.py", line=2, through=4)
    ours = stated("ours", other)

    assert not Comparison(
        ours=stated("ours", method, other),
        theirs=(stated("theirs", Site.at("app.py", 3), Site.at("app.py", 3)),),
        relation=Relation.EQUALS,
        reason="two in one method",
    ).holds()
    differ(ours, Relation.EQUALS, stated("theirs", Site.at("app.py", 3)), because="one in one")


def test_a_documented_divergence_stays_an_equality_rather_than_becoming_a_containment() -> None:
    """Naming the findings only one reader states is stronger than saying it reports more.

    A containment is satisfied by a reader that reports nothing at all, which is the failure the
    whole harness exists to catch, so a divergence written out in full keeps the relation exact.
    """
    theirs = stated("theirs", INSIDE)

    differ(stated("ours", INSIDE, ELSEWHERE), Relation.EQUALS, theirs.plus(ELSEWHERE), because="w")
    differ(stated("ours"), Relation.EQUALS, theirs.minus(INSIDE), because="narrower on purpose")
    with pytest.raises(ValueError, match="never stated"):
        theirs.minus(ELSEWHERE)


def test_a_containment_compares_the_places_and_an_equality_compares_the_counts() -> None:
    """A rule pinned to a declaration states one finding where a line reader states several.

    Multiplicity is not a claim either can make about the other, so a containment is about which
    places were named and an equality is about how many findings were named at each.
    """
    ours = stated("ours", DECLARATION)
    hedged = stated("theirs", Site.at("app.py", 3), Site.at("app.py", 5))

    differ(ours, Relation.SUPERSET, hedged, because="MCMR names the cause once")
    differ(hedged, Relation.SUBSET, ours, because="every hedge sits inside the callable")
    assert not Comparison(
        ours=ours, theirs=(hedged,), relation=Relation.EQUALS, reason="counts"
    ).holds()


def test_two_readers_are_disjoint_only_when_both_of_them_actually_spoke() -> None:
    """A silent reader is disjoint from everything, which is the weak form of every relation."""
    differ(stated("ours", INSIDE), Relation.DISJOINT, stated("theirs", ELSEWHERE), because="apart")
    assert not Comparison(
        ours=stated("ours"),
        theirs=(stated("theirs", ELSEWHERE),),
        relation=Relation.DISJOINT,
        reason="silence is not disagreement",
    ).holds()


def test_a_union_takes_several_upstream_rules_and_counts_a_shared_finding_once() -> None:
    """One MCMR rule answering what two upstream rules answer between them is its own relation."""
    differ(
        stated("ours", INSIDE, ELSEWHERE),
        Relation.UNION,
        stated("first", INSIDE),
        stated("second", ELSEWHERE, INSIDE),
        because="a place both rules name is one place",
    )
    with pytest.raises(ValueError, match="cannot be stated"):
        differ(stated("ours"), Relation.UNION, stated("only"), because="one is not a union")
    with pytest.raises(ValueError, match="cannot be stated"):
        differ(stated("ours"), Relation.EQUALS, stated("a"), stated("b"), because="two is not one")


def test_a_failed_comparison_prints_both_readers_and_the_reason_it_was_stated_for() -> None:
    """A relation that does not hold has to say which findings only one of the two reported."""
    failed = Comparison(
        ours=stated("ALL-CONT0001", INSIDE),
        theirs=(stated("ruff RET505", ELSEWHERE),),
        relation=Relation.EQUALS,
        reason="both readers answer the same question",
    )
    explained = failed.explain()

    assert not failed.holds()
    assert "ALL-CONT0001" in explained
    assert "ruff RET505" in explained
    assert "both readers answer the same question" in explained
    assert "app.py" in explained
    assert "other.py" in explained


@given(st.data())
def test_every_assembled_source_states_the_lines_its_own_shapes_predicted(
    data: st.DataObject,
) -> None:
    """A generator has an opinion of its own only if the shapes carry their answer with them.

    Whatever subset is drawn, each shape's reported line has to land on the line the assembled
    source actually holds it at, which is what makes a property over these a check rather than a
    restatement of one reader's answer.
    """
    shapes = (
        Shape(("import math",), (), frozenset({0})),
        Shape(("import json",), ("def read():", "    return json.dumps(1)"), frozenset({1})),
        Shape((), ("def alone():", "    return 1"), frozenset({0})),
    )
    source = data.draw(assembled(shapes, prologue=("# generated",)))
    lines = source.text.splitlines()

    assert lines[0] == "# generated"
    for line in source.reported:
        assert lines[line - 1] in {"import math", "def read():", "def alone():"}
    assert source.reported


def test_a_grown_tree_is_a_new_tree_every_time(tmp_path: Path) -> None:
    """A reading is cached by the tree it read, so a drawn example needs one nobody has asked."""
    trees = Trees(root=written(tmp_path, {}))

    first = trees.grow({"a.py": "x = 1\n"})
    second = trees.grow({"a.py": "x = 2\n"})

    assert first != second
    assert (first / "a.py").read_text() == "x = 1\n"
    assert (second / "a.py").read_text() == "x = 2\n"


def test_every_registered_tool_is_either_present_here_or_named_as_absent() -> None:
    """A skipped oracle proves nothing, so what could not run here is named rather than silent.

    This case skips with the whole list, which puts one line naming every absent tool into the
    suite's own summary. That is the difference between a differential suite that is green because
    it checked something and one that is green because it checked nothing.
    """
    registered = sorted(Oracle.oracles)
    absent = [tool for tool in registered if not Oracle.installed(tool)]

    assert registered
    if absent:
        pytest.skip(
            f"{len(absent)} of {len(registered)} oracles cannot run here: {', '.join(absent)}"
        )
