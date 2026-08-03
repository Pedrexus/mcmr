from mcmr.domain.contracts import (
    FixPlan,
    Inline,
    Move,
    Placement,
    Remove,
    RemoveDirectory,
    Rename,
    Replace,
    Unwrap,
)
from mcmr.facts import MemberKind, MethodAnalysis, NodeRef, SourceSpan, SymbolRef, Visibility

_SPAN = SourceSpan(path="src/service.py", start_line=4)
_OTHER = SourceSpan(path="src/service.py", start_line=9)


def node(name: str, span: SourceSpan = _SPAN) -> NodeRef:
    """Build one addressed node the engine can name."""
    return NodeRef(id=name, span=span, text=name)


def test_every_rewrite_reports_the_spans_it_touches() -> None:
    """The engine detects overlapping plans generically, so each operation owes its spans.

    Nothing else in the suite reads these, which is how they went unmeasured while a coverage
    exclusion for `...` was quietly swallowing them.
    """
    target = node("target")
    anchor = node("anchor", _OTHER)

    assert Remove(target=target).spans == [_SPAN]
    assert RemoveDirectory(target=_SPAN).spans == [_SPAN]
    assert Replace(target=target, source="value").spans == [_SPAN]
    assert Move(target=target, anchor=anchor, placement=Placement.BEFORE).spans == [_SPAN, _OTHER]
    assert Unwrap(target=target, keep=node("keep")).spans == [_SPAN]
    assert Inline(declaration=target, body=node("body"), references=[anchor]).spans == [
        _SPAN,
        _OTHER,
    ]
    assert Rename(
        symbol=SymbolRef(id="s", name="ready", declaration=target, references=[anchor]),
        name="is_ready",
    ).spans == [_SPAN, _OTHER]
    assert FixPlan(
        summary="Move and remove.",
        rewrites=[
            Move(target=target, anchor=anchor, placement=Placement.BEFORE),
            Remove(target=target),
        ],
    ).spans == [_SPAN, _OTHER, _SPAN]


def test_a_protocol_member_sorts_after_lifecycle_and_before_the_rest() -> None:
    """A language's own protocol names are a group of their own in a declared member order."""
    order = {
        "lifecycle": ("__init__",),
        "visibility_order": ("public", "private"),
        "kind_order": ("method",),
        "alphabetical": True,
    }
    protocol = MethodAnalysis(name="__repr__", span=_SPAN, is_protocol_name=True)

    assert protocol.order_key(**order) == (1, 0, 0, "__repr__")
    assert protocol.order_key(**{**order, "alphabetical": False}) == (1, 0, 0, "")

    lifecycle = MethodAnalysis(name="__init__", span=_SPAN)
    assert lifecycle.order_key(**order) == (0, 0, 0, "")

    ordinary = MethodAnalysis(
        name="Reset",
        span=_SPAN,
        visibility=Visibility.PROTECTED,
        kind=MemberKind.CLASS_METHOD,
    )
    assert ordinary.order_key(**order) == (2, 2, 1, "reset")
