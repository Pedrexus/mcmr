from functools import partial
from typing import TYPE_CHECKING, cast

import pytest

from mcmr.domain.contracts import (
    Choice,
    Edit,
    Finding,
    FixPlan,
    FixSafety,
    Inline,
    Move,
    Placement,
    Remove,
    Rename,
    Replace,
    SourceRewrite,
    Unwrap,
)
from mcmr.domain.errors import UnrenderableFix
from mcmr.facts import SymbolRef
from mcmr.presentation import PythonFixRenderer
from mcmr.presentation.fixes import (
    ByteEdit,
    EditNormalizer,
    PythonRewriteRenderer,
    RenderedFile,
)
from mcmr.presentation.reports import CheckReport

if TYPE_CHECKING:
    from pathlib import Path

from .test_operations import failure, node, render
from .test_session import rendered_files


def test_inline_keeps_the_body_before_removing_its_declaration(tmp_path: Path) -> None:
    """Inlining reads the nested body before the containing declaration disappears."""
    source = "def helper():\n    return value.strip()\n\nresult = helper()\n"
    (tmp_path / "sample.py").write_text(source)
    declaration = node(
        "sample.py",
        text="def helper():\n    return value.strip()",
        start_line=1,
        start_column=0,
        end_line=2,
        end_column=24,
        kind="function",
    )
    body = node("sample.py", text="value.strip()", start_line=2, start_column=11)
    reference = node("sample.py", text="helper()", start_line=4, start_column=9, kind="call")

    revised = render(
        tmp_path,
        Inline(declaration=declaration, body=body, references=[reference]),
    )

    assert revised == "result = value.strip()\n"


def test_renderer_refuses_stale_nodes_overlaps_and_invalid_python(tmp_path: Path) -> None:
    """A plan never guesses through stale evidence, conflicts, or a broken result."""
    (tmp_path / "sample.py").write_text("value = 1\n")
    target = node("sample.py", text="2", start_line=1, start_column=8)
    with pytest.raises(UnrenderableFix, match="expected '2'"):
        render(tmp_path, Replace(target=target, source="3"))

    target = node("sample.py", text="value", start_line=1, start_column=0)
    whole = node("sample.py", text="value = 1", start_line=1, start_column=0, kind="statement")
    with pytest.raises(UnrenderableFix, match="overlap"):
        render(
            tmp_path,
            Replace(target=target, source="answer"),
            Replace(target=whole, source="answer = 1"),
        )

    with pytest.raises(UnrenderableFix, match="does not parse"):
        render(tmp_path, Replace(target=whole, source="if"))


def test_renderer_refuses_unsupported_or_ambiguous_structural_operations(
    tmp_path: Path,
) -> None:
    """Language, identity, containment, and destination are proven rather than guessed."""
    (tmp_path / "sample.rs").write_text("let value = 1;\n")
    (tmp_path / "sample.py").write_text("value = 1\nother = 2\n")
    rust, value = (
        node("sample.rs", text="value", start_line=1, start_column=4),
        node("sample.py", text="value", start_line=1, start_column=0),
    )
    symbol = SymbolRef(
        id="value",
        name="value",
        declaration=value,
        are_references_complete=True,
    )
    cases = [
        (
            "only edits Python and Rust",
            partial(
                render,
                tmp_path,
                Replace(
                    target=node("sample.txt", text="value", start_line=1, start_column=0),
                    source="held",
                ),
            ),
        ),
        (
            "only supports exact moves",
            partial(
                PythonFixRenderer(tmp_path).render,
                failure(),
                Edit(
                    plan=FixPlan(summary="Rename.", rewrites=[Replace(target=rust, source="held")])
                ),
                "rename",
            ),
        ),
        ("would not change", partial(render, tmp_path, Replace(target=value, source="value"))),
        (
            "not an identifier",
            partial(render, tmp_path, Rename(symbol=symbol, name="not a name")),
        ),
    ]
    for message, operation in cases:
        with pytest.raises(UnrenderableFix, match=message):
            operation()


def test_renderer_refuses_ambiguous_structural_destinations(tmp_path: Path) -> None:
    """Containment must be proven before rendering."""
    (tmp_path / "sample.py").write_text("value = 1\nother = 2\n")
    (tmp_path / "other.py").write_text("other = 2\n")
    value = node("sample.py", text="value", start_line=1, start_column=0)
    other = node("sample.py", text="other", start_line=2, start_column=0)
    with pytest.raises(UnrenderableFix, match="must share one file"):
        render(
            tmp_path,
            Unwrap(
                target=value, keep=node("other.py", text="other", start_line=1, start_column=0)
            ),
        )
    with pytest.raises(UnrenderableFix, match="is not inside"):
        render(tmp_path, Unwrap(target=value, keep=other))


def test_renderer_refuses_cross_file_rust_moves(tmp_path: Path) -> None:
    """Rust declarations stay in one module until exact module rewrites are available."""
    (tmp_path / "first.rs").write_text("fn first() {}\n")
    (tmp_path / "second.rs").write_text("fn second() {}\n")
    first = node("first.rs", text="fn first() {}", start_line=1, start_column=0)
    second = node("second.rs", text="fn second() {}", start_line=1, start_column=0)
    with pytest.raises(UnrenderableFix, match="only supports exact moves"):
        PythonFixRenderer(tmp_path).render(
            failure(),
            Edit(
                plan=FixPlan(
                    summary="Move.",
                    rewrites=[Move(target=first, anchor=second, placement=Placement.BEFORE)],
                )
            ),
            "move",
        )


def test_renderer_moves_an_exact_rust_member_for_verified_review(tmp_path: Path) -> None:
    """A Rust member move preserves source and leaves parsing to fixpoint verification."""
    source = "impl Service {\n    fn zebra() {}\n\n    fn alpha() {}\n}\n"
    (tmp_path / "sample.rs").write_text(source)
    zebra = node(
        "sample.rs",
        text="fn zebra() {}",
        start_line=2,
        start_column=4,
        kind="method",
    )
    alpha = node(
        "sample.rs",
        text="fn alpha() {}",
        start_line=4,
        start_column=4,
        kind="method",
    )

    revised = render(tmp_path, Move(target=alpha, anchor=zebra, placement=Placement.BEFORE))

    assert revised == "impl Service {\n    fn alpha() {}\n\n    fn zebra() {}\n}\n"


def test_move_after_and_equal_insertions_keep_the_requested_order(tmp_path: Path) -> None:
    """Move placement and same-offset insertions stay deterministic."""
    (tmp_path / "sample.py").write_text("first = 1\nsecond = 2\n")
    first = node("sample.py", text="first = 1", start_line=1, start_column=0, kind="statement")
    second = node("sample.py", text="second = 2", start_line=2, start_column=0, kind="statement")
    assert (
        render(
            tmp_path,
            Move(target=first, anchor=second, placement=Placement.AFTER),
        )
        == "second = 2\nfirst = 1\n"
    )

    combined = EditNormalizer(
        [
            ByteEdit(path="sample.py", start=0, end=0, replacement=b"first\n"),
            ByteEdit(path="sample.py", start=0, end=0, replacement=b"second\n"),
        ]
    ).normalize()
    assert combined[0].replacement == b"first\nsecond\n"


def test_edit_normalization_rejects_invalid_ranges_and_collisions(tmp_path: Path) -> None:
    """The low-level byte program has one unambiguous operation at every position."""
    with pytest.raises(UnrenderableFix, match="ends before"):
        EditNormalizer([ByteEdit(path="sample.py", start=2, end=1, replacement=b"")]).normalize()
    duplicate = ByteEdit(path="sample.py", start=0, end=1, replacement=b"x")
    assert EditNormalizer([duplicate, duplicate]).normalize() == [duplicate]
    with pytest.raises(UnrenderableFix, match="overlap"):
        EditNormalizer(
            [
                ByteEdit(path="sample.py", start=0, end=3, replacement=b"x"),
                ByteEdit(path="sample.py", start=1, end=1, replacement=b"y"),
            ]
        ).normalize()
    with pytest.raises(TypeError, match="unsupported rewrite"):
        PythonRewriteRenderer({}).dispatch(cast("SourceRewrite", None))


def availability_case(tmp_path: Path) -> tuple[PythonFixRenderer, CheckReport]:
    """Build a report with duplicate, review-only, and unrenderable repairs."""
    (tmp_path / "sample.py").write_text("value = 1\n")
    target = node("sample.py", text="value", start_line=1, start_column=0)
    edit = Edit(
        plan=FixPlan(summary="Rename value.", rewrites=[Replace(target=target, source="held")])
    )
    number = node("sample.py", text="1", start_line=1, start_column=8)
    second = Edit(
        plan=FixPlan(summary="Replace value.", rewrites=[Replace(target=number, source="2")])
    )
    missing = Edit(
        plan=FixPlan(
            summary="Remove missing.",
            rewrites=[
                Remove(target=node("missing.py", text="missing", start_line=1, start_column=0))
            ],
        )
    )
    findings = (
        Finding(message="first", span=target.span, repair=edit),
        Finding(message="second", span=target.span, repair=edit),
        Finding(message="third", span=number.span, repair=second),
        Finding(message="choice", span=target.span, repair=Choice(question="decide")),
        Finding(
            message="review",
            span=target.span,
            repair=edit.model_copy(update={"safety": FixSafety.REVIEW}),
        ),
        Finding(message="missing one", span=target.span, repair=missing),
        Finding(message="missing two", span=target.span, repair=missing),
    )
    report = CheckReport(
        root=str(tmp_path),
        failures=(failure().model_copy(update={"findings": findings}),),
    )
    return PythonFixRenderer(tmp_path), report


def test_available_fixes_deduplicate_plans_and_refusals(tmp_path: Path) -> None:
    """One repeated plan appears once in both preview outcomes."""
    renderer, report = availability_case(tmp_path)

    fixes, refusals = renderer.available(report, FixSafety.SAFE)
    merged = renderer.merge(fixes)

    assert (len(fixes), len(refusals), "missing.py" in refusals[0].reason) == (2, 1, True)
    assert (merged[0].revised, len(merged[0].edits)) == (b"held = 2\n", 2)


def test_available_fixes_respect_limits(tmp_path: Path) -> None:
    """Preview limits stop cleanly and reject negative values."""
    renderer, report = availability_case(tmp_path)
    limited, early_refusals = renderer.available(
        report,
        FixSafety.SAFE,
        maximum=1,
    )

    assert (len(limited), early_refusals) == (1, [])
    assert renderer.available(report, maximum=0) == ([], [])
    with pytest.raises(ValueError, match="cannot be negative"):
        renderer.available(report, maximum=-1)


def test_merge_requires_exact_edit_programs(tmp_path: Path) -> None:
    """Independent rendered snapshots cannot be merged without exact byte edits."""
    (tmp_path / "sample.py").write_text("value = 1\n")
    without_edits = [
        rendered_files(RenderedFile(path="sample.py", original=b"value = 1\n", revised=revised))
        for revised in (b"held = 1\n", b"value = 2\n")
    ]
    with pytest.raises(UnrenderableFix, match="no exact edits"):
        PythonFixRenderer(tmp_path).merge(without_edits)


def test_merge_refuses_source_changed_after_preview(tmp_path: Path) -> None:
    """A source change after preview invalidates the exact edit program."""
    renderer, report = availability_case(tmp_path)
    fixes, _ = renderer.available(report, FixSafety.SAFE)
    (tmp_path / "sample.py").write_text("changed = 1\n")

    with pytest.raises(UnrenderableFix, match="changed after"):
        renderer.merge(fixes)
