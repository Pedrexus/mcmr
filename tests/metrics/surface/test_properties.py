from collections.abc import Sequence

from hypothesis import given
from hypothesis import strategies as st

from mcmr.facts import (
    Visibility,
)
from mcmr.rules.general import (
    boolean_parameter_count,
    declared_field_count,
    module_inception,
    positional_boolean_parameter,
    public_method_count,
)

from .support import (
    attribute,
    class_table,
    class_values,
    function_table,
    function_values,
    module,
    native_query,
    reach,
    retained_value,
)

_IDENTIFIER = st.text(alphabet="abcdefghijklmnop", min_size=1, max_size=6)


@given(
    st.lists(
        st.tuples(_IDENTIFIER, st.sampled_from(Visibility), st.booleans(), st.booleans()),
        max_size=8,
    )
)
def test_public_method_count_never_exceeds_the_members_declared(
    declared: Sequence[tuple[str, Visibility, bool, bool]],
) -> None:
    """The measure is a subset count, so it is bounded by the members it reads."""
    members: list[str] = []
    for name, visibility, is_protocol, is_field in declared:
        safe_name = f"m_{name}"
        prefix = "" if visibility is Visibility.PUBLIC else "_"
        stated = f"__{safe_name}__" if is_protocol else f"{prefix}{safe_name}"
        members.append(f"    {stated} = None" if is_field else f"    def {stated}(self): pass")
    body = "\n".join(members) or "    pass"
    subject = class_table({"subject.py": f"class Session:\n{body}\n"})
    answer = class_values(
        native_query(public_method_count, subject),
        subject,
    )["subject.py"]

    assert isinstance(answer, int) and 0 <= answer <= len(members)


@given(st.lists(_IDENTIFIER, min_size=1, max_size=6, unique=True))
def test_declared_field_count_follows_the_widest_owner(names: Sequence[str]) -> None:
    """One owner holding every name measures that many, and splitting them can only shrink it."""
    together = reach(*(attribute(f"service.Session.{name}") for name in names))
    apart = reach(*(attribute(f"service.Type{name}.{name}") for name in names))

    together_value = retained_value(together, declared_field_count)
    apart_value = retained_value(apart, declared_field_count)
    assert together_value == len(names)
    assert isinstance(apart_value, int)
    assert isinstance(together_value, int)
    assert apart_value <= together_value


@given(
    st.lists(
        st.tuples(_IDENTIFIER, st.booleans(), st.booleans(), st.booleans(), st.booleans()),
        max_size=6,
    )
)
def test_boolean_parameter_count_contains_the_positional_flag_count(
    declared: Sequence[tuple[str, bool, bool, bool, bool]],
) -> None:
    """Every positional flag is a flag, so this measure can never fall below the narrower one."""
    positional = [
        f"p_{index}_{name}: {'bool' if typed or annotated else 'Document'}"
        for index, (name, typed, annotated, keyword_only, receiver) in enumerate(declared)
        if not keyword_only and not receiver
    ]
    keywords = [
        f"p_{index}_{name}: {'bool' if typed or annotated else 'Document'}"
        for index, (name, typed, annotated, keyword_only, receiver) in enumerate(declared)
        if keyword_only and not receiver
    ]
    parameters = [*positional, *(["*"] if keywords else []), *keywords]
    source = f"def render({', '.join(parameters)}):\n    pass\n"
    subject = function_table({"subject.py": source})
    overall = function_values(
        native_query(boolean_parameter_count, subject),
        subject,
    )["render"]
    positional_count = function_values(
        native_query(positional_boolean_parameter, subject),
        subject,
    )["render"]
    assert isinstance(overall, int)
    assert isinstance(positional_count, int)
    assert overall >= positional_count


@given(
    package=_IDENTIFIER,
    stem=_IDENTIFIER,
    suffix=st.sampled_from(["py", "rs", "ts", "cpp"]),
)
def test_module_inception_holds_exactly_when_the_names_repeat(
    *, package: str, stem: str, suffix: str
) -> None:
    """The measure is name equality, so it must not depend on the suffix or the path above."""
    assert retained_value(module(f"src/{package}/{package}.{suffix}"), module_inception) is True
    assert retained_value(module(f"{package}/{stem}.{suffix}"), module_inception) == (
        package == stem
    )
