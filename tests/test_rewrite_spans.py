from mcmr.facts import MethodAnalysis, NodeRef, SourceSpan, SymbolRef
from mcmr.models import Inline, Move, Placement, Remove, Rename, Replace, Unwrap

SPAN = SourceSpan(path="src/service.py", start_line=4)
OTHER = SourceSpan(path="src/service.py", start_line=9)


def node(name: str, span: SourceSpan = SPAN) -> NodeRef:
    """Build one addressed node the engine can name."""
    return NodeRef(id=name, span=span, text=name)


def test_every_rewrite_reports_the_spans_it_touches() -> None:
    """The engine detects overlapping plans generically, so each operation owes its spans.

    Nothing else in the suite reads these, which is how they went unmeasured while a coverage
    exclusion for `...` was quietly swallowing them.
    """
    target = node("target")
    anchor = node("anchor", OTHER)

    assert Remove(target=target).spans == (SPAN,)
    assert Replace(target=target, source="value").spans == (SPAN,)
    assert Move(target=target, anchor=anchor, placement=Placement.BEFORE).spans == (SPAN, OTHER)
    assert Unwrap(target=target, keep=node("keep")).spans == (SPAN,)
    assert Inline(declaration=target, body=node("body"), references=[anchor]).spans == (
        SPAN,
        OTHER,
    )
    assert Rename(
        symbol=SymbolRef(id="s", name="ready", declaration=target, references=[anchor]),
        name="is_ready",
    ).spans == (SPAN, OTHER)


def test_a_protocol_member_sorts_after_lifecycle_and_before_the_rest() -> None:
    """A language's own protocol names are a group of their own in a declared member order."""
    order = {
        "lifecycle": ("__init__",),
        "visibility_order": ("public", "private"),
        "kind_order": ("method",),
        "alphabetical": True,
    }
    protocol = MethodAnalysis(name="__repr__", is_protocol_name=True)

    assert protocol.order_key(**order) == (1, 0, 0, "__repr__")
    assert protocol.order_key(**{**order, "alphabetical": False}) == (1, 0, 0, "")
