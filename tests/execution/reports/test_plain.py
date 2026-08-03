from typing import TYPE_CHECKING

import pytest

from mcmr.domain.contracts import (
    Choice,
    Finding,
    FixSafety,
    Measurement,
)
from mcmr.facts import SourceSpan
from mcmr.presentation.reports import (
    CheckFormat,
)

from .support import edit, failure, report, span, write_tree

if TYPE_CHECKING:
    from pathlib import Path

_SOURCE = "def render(value):\n    total = value + 1\n    return total\n"


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """Write the source quoted by the plain report cases."""
    return write_tree(tmp_path)


def test_a_finding_on_one_line_is_quoted_with_the_span_underlined(tree: Path) -> None:
    """The caret is the difference between a line number and a place a reader can look."""
    found = Finding(
        message="`total` is bound and never read",
        span=span(start=2, end=2, first=4, last=9),
        measurements=(Measurement(name="reads of it", value=0),),
        repair=Choice(question="drop the binding"),
    )

    rendered = CheckFormat.FULL.check(20).render(report(failure(found), root=tree))

    assert "ALL-DEMO0001 `total` is bound and never read" in rendered
    assert "  --> render.py:2:5" in rendered
    assert "2 |     total = value + 1" in rendered
    assert "  |     ^^^^^" in rendered
    assert "note: the rule read 3 where <= 0 is allowed" in rendered
    assert "note: reads of it 0" in rendered
    assert "help: drop the binding" in rendered


def test_a_finding_over_several_lines_quotes_only_its_first_and_its_last(tree: Path) -> None:
    """A class two hundred lines long is one finding, not two hundred lines of quotation."""
    found = Finding(message="`render` is too long", span=span(start=1, end=3, last=16))

    rendered = CheckFormat.FULL.check(20).render(report(failure(found), root=tree))

    assert "1 | / def render(value):" in rendered
    assert "..." in rendered
    assert "3 | |     return total" in rendered
    assert "|________________^" in rendered


def test_a_finding_whose_file_cannot_be_read_still_prints_everything_else(tmp_path: Path) -> None:
    """A synthesized span naming a file the tree never held is still worth printing."""
    found = Finding(
        message="`gone.py` keeps being reopened",
        span=SourceSpan(path="gone.py", end_column=4),
    )

    rendered = CheckFormat.FULL.check(20).render(report(failure(found), root=tmp_path))

    assert "  --> gone.py:1:1" in rendered
    assert "|" not in rendered.split("-->")[1]


def test_a_span_that_covers_nothing_is_left_as_the_arrow(tree: Path) -> None:
    """A repository-wide fact names a file, and a caret under its first line would be a lie."""
    found = Finding(message="`render.py` leans on too much", span=SourceSpan(path="render.py"))

    rendered = CheckFormat.FULL.check(20).render(report(failure(found), root=tree))

    assert "  --> render.py:1:1" in rendered
    assert "def render" not in rendered


def test_a_rule_that_has_not_migrated_still_lands_somewhere_a_reader_can_open(tree: Path) -> None:
    """Its summary and the span of the fact it read stand in for the finding it does not state."""
    rendered = CheckFormat.CONCISE.check(20).render(report(failure(), root=tree))

    assert rendered.splitlines()[0] == (
        "render.py:1:1: ALL-DEMO0001 Count what this demonstration counts. (3, allowed <= 0)"
    )


def test_only_a_repair_the_backend_can_render_earns_the_fixable_mark(tree: Path) -> None:
    """A choice somebody has to make is printed, and never dressed up as an automatic edit."""
    edited = Finding(
        message="`os` is imported and never read", span=span(), repair=edit(FixSafety.SAFE)
    )
    chosen = Finding(message="`render` is too long", span=span(), repair=Choice(question="split"))

    marked = CheckFormat.CONCISE.check(20).render(report(failure(edited), root=tree))
    unmarked = CheckFormat.CONCISE.check(20).render(report(failure(chosen), root=tree))

    assert marked.splitlines()[0].startswith("render.py:1:1: ALL-DEMO0001 [*] ")
    assert unmarked.splitlines()[0].startswith("render.py:1:1: ALL-DEMO0001 `render`")
    assert "help: split" in CheckFormat.FULL.check(20).render(report(failure(chosen), root=tree))


def test_a_repair_wanting_a_reader_first_says_so_rather_than_promising_to_be_safe(
    tree: Path,
) -> None:
    """The two marks are the two promises an edit can make, and both registers make the same one.

    An import cleanup that would take live bindings out with the unused one is still worth
    printing, and it is not `[*]`, so the mark reads the safety the repair states rather than the
    fact that some repair exists.
    """
    reviewed = Finding(
        message="`os` is imported and never read", span=span(), repair=edit(FixSafety.REVIEW)
    )
    judged = report(failure(reviewed), root=tree)

    assert (
        CheckFormat.CONCISE.check(20)
        .render(judged)
        .splitlines()[0]
        .startswith("render.py:1:1: ALL-DEMO0001 [?] ")
    )
    assert "ALL-DEMO0001 [?] " in CheckFormat.FULL.check(20).render(judged)
