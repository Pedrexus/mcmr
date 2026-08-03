from mcmr.rules.general import (
    abstract_member_left_unimplemented,
    final_class_subclassed,
    final_method_overridden,
    inherited_attribute_hides_a_method,
    initializer_called_on_a_stranger,
    overriding_method_changes_its_call_protocol,
    subclass_initializer_skips_its_base,
)

from ..support import link, member, table_value


def test_an_override_that_changes_how_a_caller_reaches_it_is_reported() -> None:
    """A property read as a method and a coroutine nobody awaits both fail far away."""
    unwrapped = link(
        declared=(member("size", "self"),),
        inherited=(member("size", "self", decorators=("property",)),),
    )
    awaited = link(
        declared=(member("read", "self", kind="async"),),
        inherited=(member("read", "self"),),
    )
    setter = link(
        declared=(member("size", "self", "value", decorators=("size.setter",)),),
        inherited=(member("size", "self", decorators=("functools.cached_property",)),),
    )
    steady = link(
        declared=(member("read", "self"),),
        inherited=(member("read", "self"),),
    )

    assert table_value(overriding_method_changes_its_call_protocol, unwrapped) == 1
    assert table_value(overriding_method_changes_its_call_protocol, awaited) == 1
    assert table_value(overriding_method_changes_its_call_protocol, setter) == 0
    assert table_value(overriding_method_changes_its_call_protocol, steady) == 0


def test_a_promise_a_concrete_subclass_never_kept_is_reported() -> None:
    """A concrete class holding an open contract raises for whoever instantiates it."""
    open_promise = link(
        declared=(member("describe", "self"),),
        inherited=(member("encode", "self", "value", decorators=("abstractmethod",)),),
    )
    under_abc = link(
        ancestor_names=("Base", "ABC"),
        declared=(member("describe", "self"),),
        inherited=(member("encode", "self", "value", decorators=("abstractmethod",)),),
    )
    still_abstract = link(
        declared=(member("decode", "self", "value", decorators=("abc.abstractmethod",)),),
        inherited=(member("encode", "self", "value", decorators=("abstractmethod",)),),
    )
    kept = link(
        declared=(member("encode", "self", "value"),),
        inherited=(member("encode", "self", "value", decorators=("abstractmethod",)),),
    )

    assert table_value(abstract_member_left_unimplemented, open_promise) == 1
    assert (
        table_value(
            abstract_member_left_unimplemented,
            open_promise,
            abstract_bases={"Base"},
        )
        == 0
    )
    assert table_value(abstract_member_left_unimplemented, under_abc) == 0
    assert table_value(abstract_member_left_unimplemented, still_abstract) == 0
    assert table_value(abstract_member_left_unimplemented, kept) == 0


def test_a_subclass_that_never_runs_the_initializer_above_it_is_reported() -> None:
    """Half a constructor ran, so the object exists with every base attribute missing."""
    skipped = link(
        declared=(member("__init__", "self"),),
        inherited=(member("__init__", "self"),),
    )
    polite = link(
        declared=(member("__init__", "self"),),
        inherited=(member("__init__", "self"),),
        initializer_calls=("super",),
    )
    direct = link(
        declared=(member("__init__", "self"),),
        inherited=(member("__init__", "self"),),
        initializer_calls=("Base",),
    )
    inherited_intact = link(inherited=(member("__init__", "self"),))
    promised = link(
        declared=(member("__init__", "self"),),
        inherited=(member("__init__", "self", decorators=("abstractmethod",)),),
    )
    grandparent = link(
        depth=2,
        declared=(member("__init__", "self"),),
        inherited=(member("__init__", "self"),),
    )

    assert [
        table_value(subclass_initializer_skips_its_base, relation)
        for relation in (skipped, polite, direct, inherited_intact, promised, grandparent)
    ] == [1, 0, 0, 0, 0, 0]


def test_an_initializer_run_on_a_class_nobody_inherits_is_reported() -> None:
    """Borrowing setup by hand binds two types together with a line nobody documented."""
    stranger = link(initializer_calls=("Session",))
    polite = link(initializer_calls=("super",))
    declared_base = link(initializer_calls=("Base",))
    second_link = link(
        base="pkg.Mixin", base_names=("Base", "Mixin"), initializer_calls=("Other",)
    )

    assert table_value(initializer_called_on_a_stranger, stranger) == 1
    assert table_value(initializer_called_on_a_stranger, polite) == 0
    assert table_value(initializer_called_on_a_stranger, declared_base) == 0
    assert table_value(initializer_called_on_a_stranger, second_link) == 0


def test_an_override_of_a_sealed_member_is_reported() -> None:
    """The base still assumes what the sealed member guaranteed and no longer gets it."""
    broken = link(
        declared=(member("balance", "self"),),
        inherited=(member("balance", "self", decorators=("typing.final",)),),
    )
    open_member = link(
        declared=(member("balance", "self"),),
        inherited=(member("balance", "self"),),
    )
    rebound = link(
        declared=(member("balance", kind="data"),),
        inherited=(member("balance", "self", decorators=("final",)),),
    )

    assert table_value(final_method_overridden, broken) == 1
    assert table_value(final_method_overridden, open_member) == 0
    assert table_value(final_method_overridden, rebound) == 0


def test_a_subclass_of_a_sealed_class_is_reported() -> None:
    """Sealing a class says its invariants were never meant to have a stranger inside."""
    assert table_value(final_class_subclassed, link(base_decorators=("final",))) is True
    assert table_value(final_class_subclassed, link(base_decorators=("typing.final",))) is True
    assert (
        table_value(
            final_class_subclassed,
            link(base_decorators=("final",), depth=2),
        )
        is False
    )
    assert table_value(final_class_subclassed, link()) is False


def test_a_method_an_ancestor_already_bound_to_data_is_reported() -> None:
    """Python resolves the instance attribute first, so the method below is never reached."""
    hidden = link(
        declared=(member("run", "self"),),
        inherited=(member("run", kind="data"),),
    )
    plain = link(
        declared=(member("run", "self"),),
        inherited=(member("run", "self"),),
    )
    mangled = link(
        declared=(member("__run", "self"),),
        inherited=(member("__run", kind="data"),),
    )

    assert table_value(inherited_attribute_hides_a_method, hidden) == 1
    assert table_value(inherited_attribute_hides_a_method, plain) == 0
    assert table_value(inherited_attribute_hides_a_method, mangled) == 0
