from typing import TYPE_CHECKING

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ...oracle import (
    Comparison,
    Oracle,
    Relation,
    Shape,
    Site,
    Trees,
    assembled,
    differ,
    written,
)
from .support import stated

if TYPE_CHECKING:
    from pathlib import Path

_DECLARATION = Site(path="app.py", line=1, through=9)
_INSIDE = Site.at("app.py", 4)
_ELSEWHERE = Site.at("other.py", 4)


def test_two_readers_are_disjoint_only_when_both_of_them_actually_spoke() -> None:
    """A silent reader is disjoint from everything, which is the weak form of every relation."""
    differ(
        stated("ours", _INSIDE), Relation.DISJOINT, stated("theirs", _ELSEWHERE), because="apart"
    )
    assert not Comparison(
        ours=stated("ours"),
        theirs=(stated("theirs", _ELSEWHERE),),
        relation=Relation.DISJOINT,
        reason="silence is not disagreement",
    ).holds()


def test_a_union_takes_several_upstream_rules_and_counts_a_shared_finding_once() -> None:
    """One MCMR rule answering what two upstream rules answer between them is its own relation."""
    differ(
        stated("ours", _INSIDE, _ELSEWHERE),
        Relation.UNION,
        stated("first", _INSIDE),
        stated("second", _ELSEWHERE, _INSIDE),
        because="a place both rules name is one place",
    )
    with pytest.raises(ValueError, match="cannot be stated"):
        differ(stated("ours"), Relation.UNION, stated("only"), because="one is not a union")
    with pytest.raises(ValueError, match="cannot be stated"):
        differ(stated("ours"), Relation.EQUALS, stated("a"), stated("b"), because="two is not one")


def test_a_failed_comparison_prints_both_readers_and_the_reason_it_was_stated_for() -> None:
    """A relation that does not hold has to say which findings only one of the two reported."""
    failed = Comparison(
        ours=stated("ALL-CONT0001", _INSIDE),
        theirs=(stated("ruff RET505", _ELSEWHERE),),
        relation=Relation.EQUALS,
        reason="both readers answer the same question",
    )
    explanation = failed.explain()

    assert not failed.holds()
    assert "ALL-CONT0001" in explanation
    assert "ruff RET505" in explanation
    assert "both readers answer the same question" in explanation
    assert "app.py" in explanation
    assert "other.py" in explanation


@given(st.data())
def test_every_assembled_source_states_the_lines_its_own_shapes_predicted(
    data: st.DataObject,
) -> None:
    """A generator has an opinion of its own only if the shapes carry their answer with them.

    Whatever subset is drawn, each shape's reported line has to land on the line the assembled
    source actually holds it at, which is what makes a property over these a check rather than a
    restatement of one reader's answer.
    """
    shapes = [
        Shape(opening=["import math"], reported={0}),
        Shape(
            opening=["import json"],
            body=["def read():", "    return json.dumps(1)"],
            reported={1},
        ),
        Shape(body=["def alone():", "    return 1"], reported={0}),
    ]
    source = data.draw(assembled(shapes, prologue=["# generated"]))
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
