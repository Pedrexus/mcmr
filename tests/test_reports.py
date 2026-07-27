from typing import TYPE_CHECKING

import pytest
from hypothesis import given
from hypothesis import strategies as st

from mcmr.engine import RuleEngine
from mcmr.facts import Fact, NodeRef, SourceSpan
from mcmr.models import (
    Choice,
    Edit,
    Finding,
    FixPlan,
    FixSafety,
    Measurement,
    Observation,
    Remove,
    Reported,
    RuleDefinition,
    RuleDocumentation,
    RuleValue,
    Unit,
    answered,
    counted,
    explained,
)
from mcmr.policy import Verdict, standard
from mcmr.reports import CheckFormat, CheckReport, RuleFailure, SourceReader
from mcmr.runs import Assessment

if TYPE_CHECKING:
    from pathlib import Path

SOURCE = "def render(value):\n    total = value + 1\n    return total\n"

values = st.one_of(
    st.booleans(),
    st.integers(min_value=-1000, max_value=1000),
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
    st.text(max_size=12),
)


def span(start: int = 1, end: int = 1, first: int = 0, last: int = 10) -> SourceSpan:
    """Return one span over the sample source, in the shape the kernel writes."""
    return SourceSpan(
        path="render.py",
        start_line=start,
        start_column=first,
        end_line=end,
        end_column=last,
    )


def definition(rule: str, output: str, unit: str = "") -> RuleDefinition:
    """Return one definition carrying only what a report and a policy read from it."""
    return RuleDefinition(
        id=rule,
        callable=f"mcmr.rules.general.deterministic.demo.r0001.{rule.lower()}",
        scope="general",
        lane="deterministic",
        family="demo",
        fact="ModuleFact",
        output=output,
        unit=unit,
        documentation=RuleDocumentation(
            summary="Count what this demonstration counts.",
            definition="A definition long enough to read.",
            examples="A body of `12` lines returns `12`.",
        ),
    )


def failure(finding: Finding | None = None, value: RuleValue = 3) -> RuleFailure:
    """Return one failure carrying at most one finding, for the renderings to print."""
    return RuleFailure(
        rule="ALL-DEMO0001",
        summary="Count what this demonstration counts.",
        where="module:render.py",
        span=span(),
        value=value,
        allowed="<= 0",
        findings=() if finding is None else (finding,),
    )


def report(*failures: RuleFailure, root: Path) -> CheckReport:
    """Return one check report over a written tree, in the shape a rendering reads."""
    return CheckReport(root=str(root), profile="standard", file_count=1, failures=failures)


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """Write the one source file every excerpt in this module quotes."""
    (tmp_path / "render.py").write_text(SOURCE)
    return tmp_path


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


def edit(safety: FixSafety) -> Edit:
    """Build one rendered edit promising as much as the safety level it was given."""
    node = NodeRef(id="render.py:0:import", span=span(), kind="import", text="import os")
    return Edit(
        plan=FixPlan(summary="Remove the import.", rewrites=[Remove(target=node)]),
        safety=safety,
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


def test_the_view_states_what_it_left_out_and_what_the_run_cost(tree: Path) -> None:
    """A bounded report that hid its own truncation would read as a shorter list of problems."""
    found = Finding(message="`total` is bound and never read", span=span())

    rendered = CheckFormat.CONCISE.check(1).render(
        report(failure(found), failure(found), failure(found), root=tree)
    )

    assert "and 2 more failures" in rendered
    assert "1 files, 0 facts, 0 invocations, 3 failures, 3 findings" in rendered


def test_a_file_is_read_once_however_many_findings_point_into_it(tree: Path) -> None:
    """The excerpt is the only part of a report that reads the tree, so it opens a file once."""
    reader = SourceReader(root=tree)

    first = reader.line("render.py", 2)
    (tree / "render.py").write_text("changed\n")

    assert first == "    total = value + 1"
    assert reader.line("render.py", 2) == "    total = value + 1"
    assert reader.line("render.py", 99) == ""


def test_a_report_states_where_every_failure_the_profile_reached_is() -> None:
    """The report is built from judged assessments, so both registers read one source."""
    judged = Assessment(
        definition=definition("ALL-DEMO0001", "int", "count"),
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


@given(value=values, message=st.text(min_size=1, max_size=20))
def test_findings_never_move_the_value_a_profile_judges(value: RuleValue, message: str) -> None:
    """Migration adds evidence, so a verdict has to be blind to whether a rule reported any."""
    engine = RuleEngine(rules=[])
    fact = Fact(key="module:render.py", span=span())
    contract = (type(value).__name__, "count", [])
    found = Finding(message=message, span=span())
    judged = definition("ALL-DEMO0001", type(value).__name__, "count")

    bare = engine.observed("demo", fact, contract, value)
    rich = engine.observed("demo", fact, contract, Reported(value=value, findings=(found,)))

    assert bare.value == rich.value
    assert bare.findings == ()
    assert rich.findings == (found,)
    assert standard().decide(judged, bare.value) == standard().decide(judged, rich.value)


@given(value=values)
def test_both_answer_shapes_read_back_through_one_seam(value: RuleValue) -> None:
    """Everything downstream reads an answer here, so the two shapes have to be one shape."""
    found = Finding(message="a finding", span=span())

    assert answered(value) == value
    assert answered(Reported(value=value, findings=(found,))) == value
    assert explained(value) == ()
    assert explained(Reported(value=value, findings=(found,))) == (found,)


@given(amount=st.integers(min_value=0, max_value=99))
def test_a_quantity_is_written_in_the_number_it_asks_for(amount: int) -> None:
    """A catalog writing `1 lines` wherever it is right once is a catalog nobody trusts."""
    written = counted(amount, "line")

    assert written == f"{amount} line{'' if amount == 1 else 's'}"
    assert counted(amount, "class", "classes").endswith("class" if amount == 1 else "classes")


def test_a_measurement_says_its_share_the_way_somebody_would_say_it() -> None:
    """A share carried to six decimal places stops being read and starts being decoded."""
    share = Measurement(name="share of the tree", value=6.329113924050633, unit=Unit.PERCENTAGE)

    assert share.rendered == "share of the tree 6.329%"
    assert Measurement(name="repeated lines", value=10).rendered == "repeated lines 10"
