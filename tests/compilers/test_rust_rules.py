from typing import TYPE_CHECKING, cast

import pytest

from mcmr.facts import (
    CloneCall,
    LifetimeAnnotation,
    RustSurfaceFact,
    SourceSpan,
    StaticLifetime,
)
from mcmr.rules.rust import (
    clone_call_count,
    clone_inside_loop,
    demanded_static_lifetime,
    elidable_lifetime_annotation,
    lifetime_annotation_count,
)

from ..support import query_value, retained_query

if TYPE_CHECKING:
    from typing import Literal

    import polars as pl

    from mcmr.query import RuleQuery


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
    required_by_syntax: list[str] | None = None,
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
        required_by_syntax=required_by_syntax or [],
    )


def rows(query: RuleQuery) -> pl.DataFrame:
    """Collect the findings emitted by one table query."""
    if query.findings is None:
        raise TypeError("the Rust rule emitted no findings relation")
    return query.findings.rows.collect()


def measurements(found: pl.DataFrame, index: int = 0) -> dict[str, float]:
    """Return one finding's named measurements."""
    names = cast("list[str]", found.get_column("measurement_names").to_list()[index])
    values = cast("list[float]", found.get_column("measurement_values").to_list()[index])
    return dict(zip(names, values, strict=True))


def test_a_lifetime_written_in_one_input_position_is_elidable() -> None:
    """Elision gives that position its own fresh lifetime, which is what the source wrote."""
    subject = surface(annotations=[annotated(parameters=["a"])])

    assert query_value(retained_query(subject, elidable_lifetime_annotation)) == 1
    assert query_value(retained_query(subject, lifetime_annotation_count)) == 1


def test_a_lifetime_required_inside_argument_impl_trait_is_not_elidable() -> None:
    """Stable Rust has no anonymous lifetime syntax for this associated type binding."""
    subject = surface(annotations=[annotated(parameters=["a"], required_by_syntax=["a"])])

    assert query_value(retained_query(subject, elidable_lifetime_annotation)) == 0


def test_a_lifetime_written_in_two_input_positions_ties_them_and_survives() -> None:
    """Elision would give each its own, so the two signatures do not mean the same thing.

    This is the shape `fn descend<'a>(node: &'a Node, found: &mut Vec<&'a Node>)` states, where
    deleting the annotation does not compile at all, and reporting it was 3 of the 13 findings
    this rule used to make on MCMR's own kernel.
    """
    subject = surface(annotations=[annotated(parameters=["a", "a"])])

    assert query_value(retained_query(subject, elidable_lifetime_annotation)) == 0


def test_a_receiver_that_carries_the_returned_lifetime_is_elidable() -> None:
    """Elision hands every elided output the receiver's lifetime whatever else is in scope."""
    carried = surface(annotations=[annotated(receiver="a", returned=["a"])])
    borrowed = surface(annotations=[annotated(returned=["a"], parameters=["a"])])

    assert query_value(retained_query(carried, elidable_lifetime_annotation)) == 1
    assert query_value(retained_query(borrowed, elidable_lifetime_annotation)) == 0


def test_an_output_lifetime_with_no_receiver_is_left_alone() -> None:
    """Its elidability turns on input arity, which lives in the type definitions."""
    subject = surface(annotations=[annotated(returned=["a"], parameters=["a"])])

    assert query_value(retained_query(subject, elidable_lifetime_annotation)) == 0


@pytest.mark.parametrize("kind", ["type", "trait", "alias"])
def test_a_declaration_with_no_elision_rule_is_never_judged(
    kind: Literal["type", "trait", "alias"],
) -> None:
    """Rust infers no lifetime for these declarations, so nothing can be compared."""
    subject = surface(annotations=[annotated(kind=kind)])

    assert query_value(retained_query(subject, elidable_lifetime_annotation)) == 0
    assert query_value(retained_query(subject, lifetime_annotation_count)) == 1


def test_a_lifetime_the_body_or_a_bound_still_needs_is_doing_work() -> None:
    """A name used past the signature cannot be dropped from it."""
    subject = surface(annotations=[annotated(parameters=["a"], beyond=["a"])])

    assert query_value(retained_query(subject, elidable_lifetime_annotation)) == 0
    unnamed = LifetimeAnnotation(owner="build", kind="function")
    assert (
        query_value(retained_query(surface(annotations=[unnamed]), elidable_lifetime_annotation))
        == 0
    )


def test_an_elidable_annotation_is_reported_at_the_line_that_states_it() -> None:
    """A count of idle annotations names the declaration and where to delete from."""
    query = retained_query(
        surface(annotations=[annotated(parameters=["a"])]),
        elidable_lifetime_annotation,
    )
    found = rows(query)

    assert query_value(query) == 1
    assert found.item(0, "message") == (
        "`build` names `'a`, which elision would have produced on its own"
    )
    assert found.item(0, "path") == "src/graph.rs"
    assert found.item(0, "start_line") == 7
    assert measurements(found) == {
        "lifetimes it states": 1,
        "input positions naming one": 1,
    }
    options = cast("list[str]", found.get_column("choice_options").to_list()[0])
    assert "delete the annotation" in options[0]


def test_a_pin_counts_only_where_it_demands_something_of_a_caller() -> None:
    """A parameter or field forecloses, while a return only promises more."""
    subject = surface(
        pins=[
            StaticLifetime(owner="describe", line=4, position="demand"),
            StaticLifetime(owner="label", line=9, position="supply"),
            StaticLifetime(owner="spawn", line=12, position="bound"),
        ]
    )
    query = retained_query(subject, demanded_static_lifetime)
    found = rows(query)

    assert query_value(query) == 1
    assert found.item(0, "message") == (
        "`describe` demands a `'static` reference, so no caller can hand it anything read at run "
        "time"
    )
    assert found.item(0, "path") == "src/graph.rs"
    assert found.item(0, "start_line") == 4
    assert measurements(found) == {
        "pins demanding here": 1,
        "pins this module states": 3,
    }


def test_a_copy_is_counted_once_and_again_for_sitting_in_a_loop() -> None:
    """Owning data is a fair trade at a function edge and a bad one inside a loop."""
    subject = surface(
        clones=[
            CloneCall(receiver="prefix", owner="run", line=3, loop_depth=0),
            CloneCall(receiver="prefix", owner="run", line=6, loop_depth=1),
            CloneCall(receiver="item", owner="run", line=8, loop_depth=2),
        ]
    )

    assert query_value(retained_query(subject, clone_call_count)) == 3
    assert query_value(retained_query(subject, clone_inside_loop)) == 2
    assert query_value(retained_query(surface(), clone_inside_loop)) == 0


def test_a_copy_inside_a_loop_names_the_value_and_how_deep_the_loop_is() -> None:
    """A count of copies names which value is being paid for on every pass."""
    query = retained_query(
        surface(clones=[CloneCall(receiver="prefix", owner="run", line=6, loop_depth=2)]),
        clone_inside_loop,
    )
    found = rows(query)

    assert query_value(query) == 1
    assert found.item(0, "message") == (
        "`run` copies `prefix` inside a loop, so the copy is paid again on every pass"
    )
    assert found.item(0, "path") == "src/graph.rs"
    assert found.item(0, "start_line") == 6
    assert measurements(found) == {
        "loops around it": 2,
        "copies this module makes": 1,
    }
    options = cast("list[str]", found.get_column("choice_options").to_list()[0])
    assert "hoist the copy above the loop" in options


def test_the_two_measures_state_every_record_they_counted_and_propose_nothing() -> None:
    """Which way to lean between borrowing and copying is the project's decision."""
    subject = surface(
        annotations=[annotated(parameters=["a"])],
        clones=[CloneCall(receiver="prefix", owner="run", line=6)],
    )
    counted = retained_query(subject, lifetime_annotation_count)
    copies = retained_query(subject, clone_call_count)
    lifetime_findings = rows(counted)
    copy_findings = rows(copies)

    assert (query_value(counted), query_value(copies)) == (1, 1)
    assert (
        lifetime_findings.item(0, "message"),
        lifetime_findings.item(0, "choice_question"),
        copy_findings.item(0, "message"),
        copy_findings.item(0, "choice_question"),
    ) == ("`build` is a function naming `'a`", "", "`run` copies `prefix` explicitly", "")
    assert measurements(copy_findings) == {
        "loops around it": 0,
        "lifetimes this module states": 1,
    }
