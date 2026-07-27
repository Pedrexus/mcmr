from typing import TYPE_CHECKING

from mcmr.facts import (
    CloneCall,
    LifetimeAnnotation,
    RustSurfaceFact,
    SourceSpan,
    StaticLifetime,
)
from mcmr.rules.rust.deterministic.lifetimes.r0001 import elidable_lifetime_annotation
from mcmr.rules.rust.deterministic.lifetimes.r0002 import demanded_static_lifetime
from mcmr.rules.rust.deterministic.lifetimes.r0003 import lifetime_annotation_count
from mcmr.rules.rust.deterministic.ownership.r0001 import clone_inside_loop
from mcmr.rules.rust.deterministic.ownership.r0002 import clone_call_count

if TYPE_CHECKING:
    from typing import Literal
from tests.conftest import measured


def surface(
    *,
    annotations: list[LifetimeAnnotation] | None = None,
    pins: list[StaticLifetime] | None = None,
    clones: list[CloneCall] | None = None,
) -> RustSurfaceFact:
    """Build one module's ownership surface from the parts a rule reads."""
    return RustSurfaceFact(
        key="surface:src/graph.rs",
        span=SourceSpan(path="src/graph.rs"),
        language="rust",
        annotations=annotations or [],
        pins=pins or [],
        clones=clones or [],
    )


def annotated(
    *,
    kind: Literal["function", "method", "type", "trait", "alias"] = "function",
    returned: list[str] | None = None,
    receiver: str = "",
    parameters: list[str] | None = None,
    beyond: list[str] | None = None,
) -> LifetimeAnnotation:
    """Build one declaration naming `'a` in whichever positions the case needs."""
    return LifetimeAnnotation(
        owner="build",
        kind=kind,
        names=["a"],
        line=7,
        returned=returned or [],
        receiver=receiver,
        parameters=parameters or [],
        beyond=beyond or [],
    )


def test_a_lifetime_written_in_one_input_position_is_elidable() -> None:
    """Elision gives that position its own fresh lifetime, which is what the source wrote."""
    subject = surface(annotations=[annotated(parameters=["a"])])

    assert elidable_lifetime_annotation(subject).value == 1
    assert lifetime_annotation_count(subject).value == 1


def test_a_lifetime_written_in_two_input_positions_ties_them_and_survives() -> None:
    """Elision would give each its own, so the two signatures do not mean the same thing.

    This is the shape `fn descend<'a>(node: &'a Node, found: &mut Vec<&'a Node>)` states, where
    deleting the annotation does not compile at all, and reporting it was 3 of the 13 findings
    this rule used to make on MCMR's own kernel.
    """
    subject = surface(annotations=[annotated(parameters=["a", "a"])])

    assert elidable_lifetime_annotation(subject).value == 0


def test_a_receiver_that_carries_the_returned_lifetime_is_elidable() -> None:
    """Elision hands every elided output the receiver's lifetime whatever else is in scope."""
    carried = surface(annotations=[annotated(receiver="a", returned=["a"])])
    borrowed = surface(annotations=[annotated(returned=["a"], parameters=["a"])])

    assert elidable_lifetime_annotation(carried).value == 1
    assert elidable_lifetime_annotation(borrowed).value == 0


def test_an_output_lifetime_with_no_receiver_is_left_alone() -> None:
    """Its elidability turns on input arity, which lives in the type definitions."""
    subject = surface(annotations=[annotated(returned=["a"], parameters=["a"])])

    assert elidable_lifetime_annotation(subject).value == 0


def test_a_declaration_with_no_elision_rule_is_never_judged() -> None:
    """Rust infers no lifetime for a type, a trait, or an alias, so nothing can be compared.

    This is the other 10 of the 13 findings the rule used to make on MCMR's own kernel, every one
    of them a struct or an alias whose annotation has no elided form at all.
    """
    for kind in ("type", "trait", "alias"):
        subject = surface(annotations=[annotated(kind=kind)])

        assert elidable_lifetime_annotation(subject).value == 0
        assert lifetime_annotation_count(subject).value == 1


def test_a_lifetime_the_body_or_a_bound_still_needs_is_doing_work() -> None:
    """A name used past the signature cannot be dropped from it."""
    subject = surface(annotations=[annotated(parameters=["a"], beyond=["a"])])

    assert elidable_lifetime_annotation(subject).value == 0
    unnamed = LifetimeAnnotation(owner="build", kind="function")
    assert elidable_lifetime_annotation(surface(annotations=[unnamed])).value == 0


def test_an_elidable_annotation_is_reported_at_the_line_that_states_it() -> None:
    """A count of idle annotations named neither the declaration nor where to delete from."""
    answer = elidable_lifetime_annotation(surface(annotations=[annotated(parameters=["a"])]))

    assert answer.findings[0].message == (
        "`build` names `'a`, which elision would have produced on its own"
    )
    assert answer.findings[0].span.location == "src/graph.rs:7"
    assert measured(answer.findings[0]) == {
        "lifetimes it states": 1,
        "input positions naming one": 1,
    }
    assert answer.findings[0].repair is not None
    assert "delete the annotation" in answer.findings[0].repair.summary


def test_a_pin_counts_only_where_it_demands_something_of_a_caller() -> None:
    """A parameter or field forecloses; a return position only promises more than it had to."""
    subject = surface(
        pins=[
            StaticLifetime(owner="describe", line=4, position="demand"),
            StaticLifetime(owner="label", line=9, position="supply"),
            StaticLifetime(owner="spawn", line=12, position="bound"),
        ]
    )
    assert demanded_static_lifetime(subject).value == 1
    answer = demanded_static_lifetime(subject)
    assert answer.findings[0].message == (
        "`describe` demands a `'static` reference, so no caller can hand it anything read at run "
        "time"
    )
    assert answer.findings[0].span.location == "src/graph.rs:4"
    assert measured(answer.findings[0]) == {
        "pins demanding here": 1,
        "pins this module states": 3,
    }


def test_a_copy_is_counted_once_and_again_for_sitting_in_a_loop() -> None:
    """Owning data is a fair trade at the edge of a function and a bad one inside a loop."""
    subject = surface(
        clones=[
            CloneCall(receiver="prefix", owner="run", line=3, loop_depth=0),
            CloneCall(receiver="prefix", owner="run", line=6, loop_depth=1),
            CloneCall(receiver="item", owner="run", line=8, loop_depth=2),
        ]
    )

    assert clone_call_count(subject).value == 3
    assert clone_inside_loop(subject).value == 2
    assert clone_inside_loop(surface()).value == 0


def test_a_copy_inside_a_loop_names_the_value_and_how_deep_the_loop_is() -> None:
    """A count of copies said nothing about which value was being paid for on every pass."""
    subject = surface(clones=[CloneCall(receiver="prefix", owner="run", line=6, loop_depth=2)])
    answer = clone_inside_loop(subject)

    assert answer.findings[0].message == (
        "`run` copies `prefix` inside a loop, so the copy is paid again on every pass"
    )
    assert answer.findings[0].span.location == "src/graph.rs:6"
    assert measured(answer.findings[0]) == {
        "loops around it": 2,
        "copies this module makes": 1,
    }
    assert answer.findings[0].repair is not None
    assert "hoist the copy above the loop" in answer.findings[0].repair.summary


def test_the_two_measures_state_every_record_they_counted_and_propose_nothing() -> None:
    """Which way a module should lean between borrowing and copying is the project's decision."""
    subject = surface(
        annotations=[annotated(parameters=["a"])],
        clones=[CloneCall(receiver="prefix", owner="run", line=6)],
    )
    counted = lifetime_annotation_count(subject)
    copies = clone_call_count(subject)

    assert counted.findings[0].message == "`build` is a function naming `'a`"
    assert counted.findings[0].repair is None
    assert copies.findings[0].message == "`run` copies `prefix` rather than borrowing it"
    assert copies.findings[0].repair is None
    assert measured(copies.findings[0]) == {
        "loops around it": 0,
        "lifetimes this module states": 1,
    }
