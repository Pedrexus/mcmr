from io import StringIO
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from mcmr.checking.session import Assessment
from mcmr.domain.contracts import (
    Choice,
    Finding,
    FixSafety,
    Measurement,
    ModelProvenance,
    Observation,
    Unit,
)
from mcmr.domain.policy import Verdict
from mcmr.facts import SourceSpan
from mcmr.presentation.reports import (
    CheckFormat,
    RichCheck,
    RuleFailure,
    SourceReader,
)

from .support import definition, edit, failure, report, span, write_tree

if TYPE_CHECKING:
    from pathlib import Path

_SOURCE = "def render(value):\n    total = value + 1\n    return total\n"


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """Write the source quoted by the rich report cases."""
    return write_tree(tmp_path)


def test_the_view_states_what_it_left_out_and_what_the_run_cost(tree: Path) -> None:
    """A bounded report that hid its own truncation would read as a shorter list of problems."""
    found = Finding(message="`total` is bound and never read", span=span())

    rendered = CheckFormat.CONCISE.check(1).render(
        report(failure(found), failure(found), failure(found), root=tree)
    )

    assert "and 2 more diagnostics" in rendered
    assert (
        "1 files, 0 facts, 0/0 rules, 0 skipped, 0 table queries, 0 observations, "
        "3 failures, 3 findings" in rendered
    )


def test_plain_view_limits_findings_within_one_failure(tree: Path) -> None:
    """One aggregate catalog verdict cannot bypass the diagnostic display bound."""
    findings = [Finding(message=f"gap {index}", span=span()) for index in range(3)]
    aggregate = failure().model_copy(update={"findings": findings})

    rendered = CheckFormat.CONCISE.check(1).render(report(aggregate, root=tree))

    assert "gap 0" in rendered
    assert "gap 1" not in rendered
    assert "and 2 more diagnostics" in rendered


def test_rich_view_groups_summary_source_and_detailed_evidence(tree: Path) -> None:
    """The default terminal view exposes detail without flattening it into an unreadable line."""
    found = Finding(
        message="`total` is bound and never read",
        span=span(start=2, end=2, first=4, last=9),
        measurements=(Measurement(name="reads", value=0),),
        evidence=("python.ast.name.load",),
        provenance=ModelProvenance(
            backend="codex",
            model="gpt-5",
            reasoning_effort="high",
            input_tokens=100,
            output_tokens=8,
            reasoning_tokens=20,
        ),
        repair=edit(FixSafety.SAFE),
    )
    view = report(failure(found), root=tree).model_copy(
        update={"fact_count": 4, "table_query_count": 2, "observation_count": 12}
    )
    stream = StringIO()

    Console(file=stream, width=110, color_system=None).print(RichCheck(limit=20).render(view))

    rendered = stream.getvalue()
    assert all(
        fragment in rendered
        for fragment in (
            "MCMR check",
            "1 files, 1 failures, 1 findings, 0 unassessed, 0 skipped",
            "Files",
            "Facts",
            "Table queries",
            "Observations",
            "python.ast.name.load",
            "codex gpt-5 with high reasoning",
            "100 input, 8 output, 20 reasoning",
            "Safe Fix",
        )
    )
    assert "PYTHON" not in rendered


def test_rich_view_states_a_clean_result(tree: Path) -> None:
    """A clean run remains explicit in the structured view."""
    stream = StringIO()
    console = Console(file=stream, width=100, color_system=None)
    console.print(RichCheck(limit=1).render(report(root=tree)))
    assert "No policy failures" in stream.getvalue()


def test_rich_view_states_a_bounded_result(tree: Path) -> None:
    """An omitted diagnostic tail remains explicit in the structured view."""
    stream = StringIO()
    console = Console(file=stream, width=100, color_system=None)
    found = Finding(message="failure", span=span())
    console.print(RichCheck(limit=1).render(report(failure(found), failure(found), root=tree)))
    assert "1 more diagnostics are outside this view" in stream.getvalue()


def test_rich_view_distinguishes_review_fixes_and_decisions(tree: Path) -> None:
    """Review-only fixes and user decisions retain distinct presentation."""
    stream = StringIO()
    reviewed = Finding(
        message="review this import",
        span=span(),
        repair=edit(FixSafety.REVIEW),
    )
    decision = Finding(
        message="choose a boundary",
        span=SourceSpan(path="missing.py", end_column=4),
        repair=Choice(question="keep or split", options=("keep", "split")),
    )
    Console(file=stream, width=100, color_system=None).print(
        RichCheck(limit=2).render(report(failure(reviewed), failure(decision), root=tree))
    )
    rendered = stream.getvalue()
    assert all(
        fragment in rendered
        for fragment in ("Review Fix", "Decision", "keep or split (keep or split)")
    )


def test_a_file_is_read_once_however_many_findings_point_into_it(tree: Path) -> None:
    """The excerpt is the only part of a report that reads the tree, so it opens a file once."""
    reader = SourceReader(root=tree)

    first = reader.line("render.py", 2)
    (tree / "render.py").write_text("changed\n")

    assert first == "    total = value + 1"
    assert reader.line("render.py", 2) == "    total = value + 1"
    assert reader.line("render.py", 99) == ""


def test_a_nonfile_source_is_absent_but_a_broken_source_still_fails(tree: Path) -> None:
    """A missing file or directory has no excerpt while corrupt source remains an error."""
    reader = SourceReader(root=tree)

    assert reader.line("deleted.py", 1) == ""
    (tree / "package").mkdir()
    assert reader.line("package", 1) == ""
    (tree / "broken.py").write_bytes(b"\xff")
    with pytest.raises(UnicodeDecodeError):
        reader.line("broken.py", 1)


def test_a_report_states_where_every_policy_failure_is() -> None:
    """The report is built from judged assessments, so both registers read one source."""
    judged = Assessment(
        definition=definition("ALL-DEMO0001", output="int", unit="count"),
        observation=Observation(
            rule="mcmr.rules.general.deterministic.demo.r0001.all_demo0001",
            fact="module:render.py",
            value=12,
            span=span(end=3),
        ),
        verdict=Verdict.FAIL,
    )

    built = RuleFailure.of(judged, "<= 0")

    assert built.rule == "ALL-DEMO0001"
    assert built.summary == "Count what this demonstration counts."
    assert built.span.location == "render.py:1-3"
    assert built.reported[0].message == "Count what this demonstration counts."


def test_a_measurement_says_its_share_the_way_somebody_would_say_it() -> None:
    """A share carried to six decimal places stops being read and starts being decoded."""
    share = Measurement(name="share of the tree", value=6.329113924050633, unit=Unit.PERCENTAGE)

    assert share.rendered == "share of the tree 6.329%"
    assert Measurement(name="repeated lines", value=10).rendered == "repeated lines 10"
