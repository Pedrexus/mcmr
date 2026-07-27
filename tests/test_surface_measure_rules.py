from hypothesis import given
from hypothesis import strategies as st

from mcmr.facts import (
    ClassAnalysis,
    ClassFact,
    FunctionFact,
    FunctionParameter,
    MemberKind,
    MethodAnalysis,
    ModuleFact,
    OverrideFact,
    SourceSpan,
    SymbolReach,
    SymbolReachFact,
    Visibility,
)
from mcmr.rules.general.deterministic.classes.r0007 import public_method_count
from mcmr.rules.general.deterministic.classes.r0008 import declared_field_count
from mcmr.rules.general.deterministic.classes.r0009 import ancestor_count
from mcmr.rules.general.deterministic.modules.r0003 import module_inception
from mcmr.rules.general.deterministic.parameters.r0003 import positional_boolean_parameter
from mcmr.rules.general.deterministic.parameters.r0004 import boolean_parameter_count

IDENTIFIER = st.text(alphabet="abcdefghijklmnop", min_size=1, max_size=6)


def classes(*declared: ClassAnalysis) -> ClassFact:
    """Return one class fact holding the given analyses under a shared module span."""
    return ClassFact(
        key="classes:src/service.py",
        span=SourceSpan(path="src/service.py"),
        classes=list(declared),
    )


def analysis(name: str, *members: MethodAnalysis) -> ClassAnalysis:
    """Return one class analysis declaring the given members in source order."""
    return ClassAnalysis(name=name, path="src/service.py", methods=list(members))


def member(
    name: str,
    *,
    kind: MemberKind = MemberKind.METHOD,
    visibility: Visibility = Visibility.PUBLIC,
    is_protocol_name: bool = False,
) -> MethodAnalysis:
    """Return one declared member with an explicit kind, visibility, and protocol marking."""
    return MethodAnalysis(
        name=name,
        kind=kind,
        visibility=visibility,
        is_protocol_name=is_protocol_name,
    )


def reach(*declarations: SymbolReach) -> SymbolReachFact:
    """Return one reach fact holding the given resolved declarations of a module."""
    return SymbolReachFact(
        key="reach:src/service.py",
        span=SourceSpan(path="src/service.py"),
        declarations=list(declarations),
    )


def attribute(qualname: str) -> SymbolReach:
    """Return one resolved data member of the type its qualified name names."""
    return SymbolReach(qualname=qualname, kind="attribute")


def link(derived: str, base: str, *, depth: int = 1, **changes: list[str]) -> OverrideFact:
    """Return one inheritance link between a derived class and one of its ancestors."""
    return OverrideFact.model_validate(
        {
            "key": f"override:{derived}:{base}",
            "span": SourceSpan(path="src/service.py"),
            "derived": derived,
            "base": base,
            "depth": depth,
        }
        | changes
    )


def module(path: str) -> ModuleFact:
    """Return one module fact located at the given repository-relative path."""
    return ModuleFact(key=f"module:{path}", span=SourceSpan(path=path))


def function(*parameters: FunctionParameter) -> FunctionFact:
    """Return one callable fact declaring the given parameters in order."""
    return FunctionFact(
        key="function:render",
        span=SourceSpan(path="src/service.py"),
        name="render",
        parameters=list(parameters),
    )


def test_public_method_count_reads_the_widest_type_in_the_module() -> None:
    wide = analysis(
        "Session",
        member("open"),
        member("read"),
        member("close"),
        member("__init__", kind=MemberKind.CONSTRUCTOR, is_protocol_name=True),
        member("__repr__", is_protocol_name=True),
        member("_reset", visibility=Visibility.PROTECTED),
        member("__cache", visibility=Visibility.PRIVATE),
        member("host", kind=MemberKind.FIELD),
    )
    narrow = analysis("Row", member("value", kind=MemberKind.PROPERTY))

    assert public_method_count(classes(wide, narrow)) == 3
    assert public_method_count(classes(narrow)) == 1
    assert public_method_count(classes()) == 0


def test_declared_field_count_groups_members_under_the_type_declaring_them() -> None:
    subject = reach(
        attribute("service.Session.host"),
        attribute("service.Session.port"),
        attribute("service.Session.timeout"),
        attribute("service.Row.value"),
        SymbolReach(qualname="service.Session.open", kind="method"),
        SymbolReach(qualname="service.LIMIT", kind="variable", is_module_scope=True),
    )

    assert declared_field_count(subject) == 3
    assert declared_field_count(reach(attribute("service.Row.value"))) == 1
    assert declared_field_count(reach()) == 0


def test_ancestor_count_reports_once_at_the_first_declared_base() -> None:
    primary = link(
        "service.Report",
        "service.Record",
        base_names=["Record"],
        ancestor_names=["Record", "Row"],
    )

    assert ancestor_count(primary) == 2
    assert ancestor_count(primary.model_copy(update={"depth": 2})) == 0
    assert ancestor_count(primary.model_copy(update={"base": "service.Row"})) == 0
    assert ancestor_count(primary.model_copy(update={"base_names": []})) == 0


def test_boolean_parameter_count_reads_every_flag_whatever_its_position() -> None:
    subject = function(
        FunctionParameter(name="self", is_receiver=True, type_name="bool"),
        FunctionParameter(name="document", type_name="Document"),
        FunctionParameter(name="inline", type_name="bool"),
        FunctionParameter(name="minified", has_boolean_annotation=True, is_keyword_only=True),
        FunctionParameter(name="strict", has_boolean_default=True, is_keyword_only=True),
    )

    assert boolean_parameter_count(subject) == 3
    assert boolean_parameter_count(function()) == 0


def test_module_inception_reports_only_an_exact_repetition() -> None:
    assert module_inception(module("src/parser/parser.py"))
    assert module_inception(module("crates/parser/parser.rs"))
    assert not module_inception(module("src/parser/lexer.py"))
    assert not module_inception(module("src/parser/__init__.py"))
    assert not module_inception(module("src/parser/mod.rs"))
    assert not module_inception(module("src/parser/parser_table.py"))


@given(
    st.lists(
        st.tuples(IDENTIFIER, st.sampled_from(Visibility), st.booleans(), st.booleans()),
        max_size=8,
    )
)
def test_public_method_count_never_exceeds_the_members_declared(
    declared: list[tuple[str, Visibility, bool, bool]],
) -> None:
    """The measure is a subset count, so it is bounded by the members it reads."""
    members = [
        member(
            name,
            kind=MemberKind.FIELD if is_field else MemberKind.METHOD,
            visibility=visibility,
            is_protocol_name=is_protocol,
        )
        for name, visibility, is_protocol, is_field in declared
    ]
    subject = classes(analysis("Session", *members))

    assert 0 <= public_method_count(subject) <= len(members)


@given(st.lists(IDENTIFIER, min_size=1, max_size=6, unique=True))
def test_declared_field_count_follows_the_widest_owner(names: list[str]) -> None:
    """One owner holding every name measures that many, and splitting them can only shrink it."""
    together = reach(*(attribute(f"service.Session.{name}") for name in names))
    apart = reach(*(attribute(f"service.Type{name}.{name}") for name in names))

    assert declared_field_count(together) == len(names)
    assert declared_field_count(apart) <= declared_field_count(together)


@given(
    st.lists(
        st.tuples(IDENTIFIER, st.booleans(), st.booleans(), st.booleans(), st.booleans()),
        max_size=6,
    )
)
def test_boolean_parameter_count_contains_the_positional_flag_count(
    declared: list[tuple[str, bool, bool, bool, bool]],
) -> None:
    """Every positional flag is a flag, so this measure can never fall below the narrower one."""
    subject = function(
        *(
            FunctionParameter(
                name=name,
                type_name="bool" if typed else "Document",
                has_boolean_annotation=annotated,
                is_keyword_only=keyword_only,
                is_receiver=receiver,
            )
            for name, typed, annotated, keyword_only, receiver in declared
        )
    )

    assert boolean_parameter_count(subject) >= positional_boolean_parameter(subject)


@given(IDENTIFIER, IDENTIFIER, st.sampled_from(["py", "rs", "ts", "cpp"]))
def test_module_inception_holds_exactly_when_the_names_repeat(
    package: str, stem: str, suffix: str
) -> None:
    """The measure is name equality, so it must not depend on the suffix or the path above."""
    assert module_inception(module(f"src/{package}/{package}.{suffix}"))
    assert module_inception(module(f"{package}/{stem}.{suffix}")) == (package == stem)
