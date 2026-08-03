import pytest

from mcmr.facts import ModuleFact

from ...oracle import (
    Comparison,
    DeclarationReader,
    Oracle,
    Reader,
    Relation,
    Site,
    differ,
)
from .support import stated

_DECLARATION = Site(path="app.py", line=1, through=9)
_INSIDE = Site.at("app.py", 4)
_ELSEWHERE = Site.at("other.py", 4)


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
    assert _DECLARATION.holds(_INSIDE)
    assert not _DECLARATION.holds(_ELSEWHERE)
    assert _DECLARATION.width == 9
    assert _INSIDE.width == 1


def test_a_report_counts_two_findings_on_one_line_as_two() -> None:
    """A multiset rather than a set, since a reader that found one of them has not agreed."""
    twice = stated("ours", _INSIDE, _INSIDE)

    assert twice.states(_INSIDE, _INSIDE)
    assert not twice.states(_INSIDE)
    assert not Comparison(
        ours=twice, theirs=(stated("theirs", _INSIDE),), relation=Relation.EQUALS, reason="two"
    ).holds()


def test_a_line_pinned_reader_is_folded_into_the_declaration_a_rule_answered_for() -> None:
    """Each reader pins a finding as precisely as its evidence allows, so one has to move.

    The finer side is expressed in the coarser side's ranges, which is what lets a rule reading a
    whole callable be compared against a tool naming a line inside it, and a finding in some other
    file stays exactly where it is so the disagreement is visible.
    """
    ours = stated("ours", _DECLARATION)
    theirs = stated("theirs", _INSIDE)

    differ(ours, Relation.EQUALS, theirs, because="the line sits inside the declaration")
    assert not Comparison(
        ours=ours,
        theirs=(stated("theirs", _ELSEWHERE),),
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
    theirs = stated("theirs", _INSIDE)

    differ(
        stated("ours", _INSIDE, _ELSEWHERE), Relation.EQUALS, theirs.plus(_ELSEWHERE), because="w"
    )
    differ(stated("ours"), Relation.EQUALS, theirs.minus(_INSIDE), because="narrower on purpose")
    with pytest.raises(ValueError, match="never stated"):
        theirs.minus(_ELSEWHERE)


def test_a_containment_compares_the_places_and_an_equality_compares_the_counts() -> None:
    """A rule pinned to a declaration states one finding where a line reader states several.

    Multiplicity is not a claim either can make about the other, so a containment is about which
    places were named and an equality is about how many findings were named at each.
    """
    ours = stated("ours", _DECLARATION)
    hedged = stated("theirs", Site.at("app.py", 3), Site.at("app.py", 5))

    differ(ours, Relation.SUPERSET, hedged, because="MCMR names the cause once")
    differ(hedged, Relation.SUBSET, ours, because="every hedge sits inside the callable")
    assert not Comparison(
        ours=ours, theirs=(hedged,), relation=Relation.EQUALS, reason="counts"
    ).holds()
