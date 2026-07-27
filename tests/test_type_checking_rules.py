import pytest

from mcmr.facts import (
    CallFact,
    CallSite,
    Expression,
    ImportBindingFact,
    NodeRef,
    ProjectConfigurationFact,
    PythonTargetConfiguration,
    SourceSpan,
    SymbolFact,
    TypeAnnotation,
    TypeAnnotationFact,
    TypingScope,
)
from mcmr.rules.python.deterministic.type_checking.r0001 import deprecated_future_annotations
from mcmr.rules.python.deterministic.type_checking.r0002 import nullable_boolean_annotation
from mcmr.rules.python.deterministic.type_checking.r0003 import minimum_python_declaration
from mcmr.rules.python.deterministic.type_checking.r0004 import prohibited_annotation
from mcmr.rules.python.deterministic.type_checking.r0005 import repeated_cast_patterns
from mcmr.rules.python.deterministic.type_checking.r0006 import shared_typings_module_candidate
from mcmr.rules.python.deterministic.type_checking.r0007 import repeated_annotated_constraint
from mcmr.rules.python.deterministic.type_checking.r0008 import redundant_boolean_conversion

SPAN = SourceSpan(path="src/example.py")


def annotations(*declared: TypeAnnotation) -> TypeAnnotationFact:
    """Return one annotation fact holding the given resolved annotations."""
    return TypeAnnotationFact(key="annotations", span=SPAN, annotations=list(declared))


def calls(*sites: CallSite) -> CallFact:
    """Return one call fact holding the given resolved call sites."""
    return CallFact(key="calls", span=SPAN, calls=list(sites))


def cast_of(module: str, path: str) -> CallSite:
    """Return one cast of a table lookup, spelled through the given typing module."""
    return CallSite(
        qualified_name=f"{module}.cast",
        path=path,
        arguments=[
            Expression(text="Type"),
            Expression(text="table.get(key)", qualified_name="table.get"),
        ],
    )


def test_future_annotations_cases() -> None:
    subject = ImportBindingFact(
        key="future import",
        span=SPAN,
        name="annotations",
        module="__future__",
        imported_name="annotations",
    )
    assert deprecated_future_annotations(subject)
    assert not deprecated_future_annotations(subject, python_minor=13)
    assert not deprecated_future_annotations(subject.model_copy(update={"module": "typing"}))


def test_annotation_shape_cases() -> None:
    """One resolved annotation is read for its union, for its names, and for its constraint.

    A nullable flag is a two-member union of `bool` and `None` and nothing wider, a prohibited
    name is counted once per resolved name the project refuses, and a constraint recipe counts
    only while it repeats across modules that could have shared a typings module instead.
    """
    nullable = annotations(
        TypeAnnotation(path="a.py", union_members=["bool", "None"]),
        TypeAnnotation(path="a.py", union_members=["bool", "None", "str"]),
        TypeAnnotation(path="a.py", union_members=["bool"]),
    )
    assert nullable_boolean_annotation(nullable) == 1

    named = annotations(
        TypeAnnotation(path="a.py", resolved_names=["typing.Any", "builtins.object"]),
        TypeAnnotation(path="a.py", resolved_names=["domain.ObjectId"]),
    )
    assert prohibited_annotation(named) == 2
    assert prohibited_annotation(named, prohibited=("Any",)) == 1

    recipe = "Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]"
    constrained = annotations(
        TypeAnnotation(path="a.py", constraint_recipe=recipe),
        TypeAnnotation(path="b.py", constraint_recipe=recipe),
        TypeAnnotation(path="b.py", constraint_recipe=recipe),
        TypeAnnotation(path="c.py", constraint_recipe="Annotated[int, Ge(0)]"),
    )
    assert repeated_annotated_constraint(constrained) == 1
    assert repeated_annotated_constraint(constrained, minimum_repetitions=4) == 0
    shared = annotations(
        *constrained.annotations,
        TypeAnnotation(path="typings.py", constraint_recipe=recipe),
    )
    assert repeated_annotated_constraint(shared) == 0


def test_minimum_python_target_cases() -> None:
    complete = ProjectConfigurationFact(
        key="python target",
        span=SPAN,
        python_target=PythonTargetConfiguration(
            project_minimum_minor=14,
            configured_tools=["ruff", "ty"],
            tool_target_minors={"ruff": 14, "ty": 14},
            per_file_target_minors=[14],
        ),
    )
    assert minimum_python_declaration(complete) == 0
    inconsistent = complete.model_copy(
        update={
            "python_target": PythonTargetConfiguration(
                project_minimum_minor=13,
                configured_tools=["ruff", "ty"],
                tool_target_minors={"ruff": 13},
                per_file_target_minors=[12],
            )
        }
    )
    assert minimum_python_declaration(inconsistent) == 3
    assert minimum_python_declaration(complete.model_copy(update={"python_target": None})) == 1
    with pytest.raises(ValueError, match="Unsupported minimum Python version"):
        minimum_python_declaration(complete, minimum_version="latest")


def test_typing_call_cases() -> None:
    """A call stands in for typing twice over, once as a repeated cast and once as a conversion.

    The cast pattern counts one accessor cast the same way in enough files to be worth typing at
    the source, whatever typing module spelled it, and the conversion counts only where the
    argument already resolves to `bool` and the builtin name was not shadowed.
    """
    casts = calls(
        cast_of("typing", "a.py"),
        cast_of("typing_extensions", "b.py"),
        cast_of("typing", "c.py"),
        CallSite(qualified_name="builtins.str", path="a.py"),
    )
    assert repeated_cast_patterns(casts) == 1
    assert repeated_cast_patterns(casts, minimum_repetitions=4) == 0

    conversions = calls(
        CallSite(
            qualified_name="builtins.bool",
            path="a.py",
            arguments=[Expression(text="fragile", resolved_type="bool")],
            node=NodeRef(id="bool-call", span=SPAN, text="bool(fragile)"),
        ),
        CallSite(
            qualified_name="builtins.bool",
            path="a.py",
            arguments=[Expression(text="items")],
        ),
        CallSite(
            qualified_name="builtins.bool",
            path="a.py",
            arguments=[Expression(text="x", resolved_type="bool")],
            is_shadowed=True,
        ),
    )
    assert redundant_boolean_conversion(conversions) == 1


def test_shared_typings_scope_cases() -> None:
    subject = SymbolFact(
        key="types",
        span=SPAN,
        typing_scopes=[
            TypingScope(
                path="src/payments",
                definitions=["A", "B", "C", "D", "E", "F"],
                reused_definitions=["A", "B", "C"],
                cross_module_import_count=4,
                definitions_outside_preferred_module=["src/payments/a.py"],
            ),
            TypingScope(
                path="src/local",
                definitions=["A", "B"],
                reused_definitions=["A"],
                cross_module_import_count=1,
                definitions_outside_preferred_module=["src/local/a.py"],
            ),
        ],
    )
    assert shared_typings_module_candidate(subject) == 6
    accepted = subject.model_copy(
        update={
            "typing_scopes": [
                subject.typing_scopes[0].model_copy(
                    update={"definitions_outside_preferred_module": ["src/payments/typings.py"]}
                )
            ]
        }
    )
    assert shared_typings_module_candidate(accepted) == 0
