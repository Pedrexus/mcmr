from mcmr.rules.general import (
    overriding_method_accepts_different_arguments,
    overriding_method_demands_an_argument_the_base_defaulted,
    overriding_method_renames_a_parameter,
)

from ..support import link, member, table_value


def test_an_override_that_stops_accepting_what_the_base_accepts_is_reported() -> None:
    """A caller holding the base passes an argument the override can no longer take."""
    narrowed = link(
        declared=(member("load", "self", "path"),),
        inherited=(member("load", "self", "path", "encoding"),),
    )
    widened = link(
        declared=(member("load", "self", "path", "encoding"),),
        inherited=(member("load", "self", "path"),),
    )
    extended = link(
        declared=(member("load", "self", "path", "encoding=None"),),
        inherited=(member("load", "self", "path"),),
    )
    variadic = link(
        declared=(member("load", "self", "*args"),),
        inherited=(member("load", "self", "path", "encoding"),),
    )
    tail_lost = link(
        declared=(member("load", "self", "path"),),
        inherited=(member("load", "self", "path", "*rest"),),
    )
    mapping_lost = link(
        declared=(member("load", "self", "path"),),
        inherited=(member("load", "self", "path", "**rest"),),
    )
    counted_and_lost = link(
        declared=(member("load", "self"),),
        inherited=(member("load", "self", "path", "*rest"),),
    )

    assert [
        table_value(overriding_method_accepts_different_arguments, relation)
        for relation in (
            narrowed,
            widened,
            extended,
            variadic,
            tail_lost,
            mapping_lost,
            counted_and_lost,
        )
    ] == [1, 1, 0, 0, 1, 1, 2]


def test_a_keyword_only_parameter_is_reached_by_its_name_and_by_nothing_else() -> None:
    """Adding, dropping, or renaming one deletes an argument rather than moving it."""
    added = link(
        declared=(member("load", "self", "path", "*", "mode"),),
        inherited=(member("load", "self", "path", "*", "flag"),),
    )
    optional = link(
        declared=(member("load", "self", "path", "*", "flag", "mode=None"),),
        inherited=(member("load", "self", "path", "*", "flag"),),
    )
    dropped = link(
        declared=(member("load", "self", "path"),),
        inherited=(member("load", "self", "path", "*", "flag"),),
    )
    absorbed = link(
        declared=(member("load", "self", "path", "**rest"),),
        inherited=(member("load", "self", "path", "*", "flag"),),
    )
    kept = link(
        declared=(member("load", "self", "path", "*", "flag"),),
        inherited=(member("load", "self", "path", "*", "flag"),),
    )

    assert [
        table_value(overriding_method_accepts_different_arguments, relation)
        for relation in (added, optional, dropped, absorbed, kept)
    ] == [1, 0, 1, 0, 0]
    assert table_value(overriding_method_renames_a_parameter, added) == 0


def test_a_position_no_caller_can_name_counts_as_an_argument_and_never_as_a_name() -> None:
    """A slot dropped breaks every caller, and a slot renamed breaks nobody who could name it."""
    dropped = link(
        declared=(member("load", "self", "path", "/"),),
        inherited=(member("load", "self", "path", "encoding", "/"),),
    )
    renamed = link(
        declared=(member("load", "self", "target", "/", "encoding"),),
        inherited=(member("load", "self", "path", "/", "encoding"),),
    )
    absorbed = link(
        declared=(member("load", "self", "path", "/", "*rest"),),
        inherited=(member("load", "self", "path", "encoding", "/"),),
    )

    assert table_value(overriding_method_accepts_different_arguments, dropped) == 1
    assert table_value(overriding_method_accepts_different_arguments, renamed) == 0
    assert table_value(overriding_method_renames_a_parameter, renamed) == 0
    assert table_value(overriding_method_accepts_different_arguments, absorbed) == 0


def test_a_name_python_owns_or_rewrites_is_outside_the_substitution_contract() -> None:
    """No caller can substitute through a mangled name and the interpreter calls the rest."""
    mangled = link(
        declared=(member("__helper", "self"),),
        inherited=(member("__helper", "self", "value"),),
    )
    inherited_data = link(
        declared=(member("run", "self"),),
        inherited=(member("run", kind="data"),),
    )
    declared_data = link(
        declared=(member("run", kind="data"),),
        inherited=(member("run", "self", "value"),),
    )
    setter = link(
        declared=(member("size", "self", "value", decorators=("size.setter",)),),
        inherited=(member("size", "self"),),
    )

    assert table_value(overriding_method_accepts_different_arguments, mangled) == 0
    assert table_value(overriding_method_accepts_different_arguments, inherited_data) == 0
    assert table_value(overriding_method_accepts_different_arguments, declared_data) == 0
    assert table_value(overriding_method_accepts_different_arguments, setter) == 0


def test_an_override_that_changes_a_parameter_name_is_reported() -> None:
    """Every ordinary parameter is also a keyword, so a rename deletes part of the interface."""
    renamed = link(
        declared=(member("save", "self", "entry"),),
        inherited=(member("save", "self", "record"),),
    )
    reordered = link(
        declared=(member("send", "self", "timeout", "payload"),),
        inherited=(member("send", "self", "payload", "timeout"),),
    )
    placeholder = link(
        declared=(member("save", "self", "record"),),
        inherited=(member("save", "self", "_unused"),),
    )
    counted = link(
        declared=(member("save", "self", "entry"),),
        inherited=(member("save", "self", "record", "stamp"),),
    )
    receiver = link(
        declared=(member("build", "klass", "value", decorators=("classmethod",)),),
        inherited=(member("build", "cls", "value", decorators=("classmethod",)),),
    )
    kept = link(
        declared=(member("save", "self", "record"),),
        inherited=(member("save", "self", "record"),),
    )

    assert [
        table_value(overriding_method_renames_a_parameter, relation)
        for relation in (renamed, reordered, placeholder, counted, receiver, kept, link())
    ] == [1, 2, 0, 0, 0, 0, 0]


def test_an_override_that_withdraws_a_default_the_base_offered_is_reported() -> None:
    """Every call keeps its shape and only the calls that relied on the default break."""
    withdrawn = link(
        declared=(member("send", "self", "timeout"),),
        inherited=(member("send", "self", "timeout=30"),),
    )
    relaxed = link(
        declared=(member("send", "self", "timeout=30"),),
        inherited=(member("send", "self", "timeout"),),
    )
    swallowed = link(
        declared=(member("send", "self", "timeout", "*rest"),),
        inherited=(member("send", "self", "timeout=30"),),
    )
    renamed = link(
        declared=(member("send", "self", "delay"),),
        inherited=(member("send", "self", "timeout=30"),),
    )
    counted = link(
        declared=(member("send", "self"),),
        inherited=(member("send", "self", "timeout=30"),),
    )
    keyword = link(
        declared=(member("send", "self", "*", "flag"),),
        inherited=(member("send", "self", "*", "flag=True"),),
    )

    assert [
        table_value(overriding_method_demands_an_argument_the_base_defaulted, relation)
        for relation in (withdrawn, relaxed, swallowed, renamed, counted, keyword, link())
    ] == [1, 0, 0, 0, 0, 0, 0]
