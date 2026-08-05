from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

import pytest

from mcmr.domain.contracts import FixSafety, RuleContract, RuleSetting, RuleValue
from mcmr.facts import (
    CallFact,
    ImportBindingFact,
    ProjectConfigurationFact,
    PythonTargetConfiguration,
    SourceSpan,
    TypeAnnotation,
    TypeAnnotationFact,
    TypingDefinition,
    TypingReuse,
    TypingScope,
)
from mcmr.plugins import Fact, RepositoryTables, Table, fact_table
from mcmr.query import RuleQuery
from mcmr.rules.python import (
    future_annotations_import,
    minimum_python_declaration,
    nullable_boolean_annotation,
    prohibited_annotation,
    redundant_boolean_conversion,
    repeated_annotated_constraint,
    repeated_cast_patterns,
)
from mcmr.table import AnalysisSession, ImportBindingRelation

from ..support import query_value, retained_query, written

_SPAN = SourceSpan(path="src/example.py")


def native_query[Family: Fact](
    rule: RuleContract,
    subject: Table[Family],
    **settings: RuleSetting,
) -> RuleQuery:
    """Invoke one specialized rule once over the complete native table."""
    result = rule.invoke_table(subject, settings=settings, dependencies={})
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic typing rule returned a model query")
    return result


def call_table(sources: dict[str, str]) -> Table[CallFact]:
    """Parse one source corpus into specialized native call relations."""
    with TemporaryDirectory() as directory:
        return AnalysisSession(
            written(Path(directory), sources),
            suffixes=(".py",),
            typed_families=(CallFact,),
        ).call_tables()


def import_table(sources: dict[str, str]) -> Table[ImportBindingFact]:
    """Parse one source corpus into specialized native import relations."""
    with TemporaryDirectory() as directory:
        return AnalysisSession(
            written(Path(directory), sources),
            suffixes=(".py",),
            typed_families=(ImportBindingFact,),
        ).import_binding_tables()


def project_table(python_minor: int) -> Table[ProjectConfigurationFact]:
    """Retain one project target for a rule that depends on repository configuration."""
    return fact_table(
        ProjectConfigurationFact,
        [
            ProjectConfigurationFact(
                key="configuration:pyproject",
                span=_SPAN,
                python_target=PythonTargetConfiguration(project_minimum_minor=python_minor),
            )
        ],
    )


def annotation_table(sources: dict[str, str]) -> Table[TypeAnnotationFact]:
    """Parse one source corpus into generic normalized annotation relations."""
    with TemporaryDirectory() as directory:
        return AnalysisSession(
            written(Path(directory), sources),
            suffixes=(".py",),
            typed_families=(TypeAnnotationFact,),
        ).table(TypeAnnotationFact)


def retained_value(subject: Fact, rule: RuleContract, **settings: RuleSetting) -> RuleValue:
    """Return one scalar from a generic rule invoked once over retained evidence."""
    return query_value(retained_query(subject, rule, **settings))


def integer_total(result: RuleQuery) -> int:
    """Sum one integer observation over every fact in a native table query."""
    total = result.values.collect().get_column("integer_value").drop_nulls().sum()
    if isinstance(total, bool) or not isinstance(total, int):
        raise TypeError("the typing rule did not emit integer values")
    return total


def future_annotations_query(subject: Table[ImportBindingFact], python_minor: int) -> RuleQuery:
    """Run the future-annotations rule with one explicit project target."""
    tables = RepositoryTables()
    tables.add(subject)
    tables.add(project_table(python_minor))
    result = future_annotations_import.invoke(tables, settings={}, dependencies={})
    if not isinstance(result, RuleQuery):
        raise TypeError("the deterministic typing rule returned a model query")
    return result


def annotations(*declared: TypeAnnotation) -> TypeAnnotationFact:
    """Return one annotation fact holding the given resolved annotations."""
    return TypeAnnotationFact(key="annotations", span=_SPAN, annotations=list(declared))


def typing_definition(name: str, *, path: str = "src/payments/a.py") -> TypingDefinition:
    """Return one located typing declaration."""
    return TypingDefinition(name=name, span=SourceSpan(path=path))


def typing_reuse(
    name: str,
    *importing_paths: str,
    path: str = "src/payments/a.py",
) -> TypingReuse:
    """Return one located typing declaration and its exact importing modules."""
    return TypingReuse(
        name=name,
        span=SourceSpan(path=path),
        importing_spans=[SourceSpan(path=item) for item in importing_paths],
    )


def test_typing_scope_and_reuse_reject_every_ambiguous_identity() -> None:
    definition = typing_definition("A")
    reuse = typing_reuse("A", "src/payments/use.py")
    invalid_scopes = [
        ([definition, definition], [], "repeats a declaration"),
        ([definition], [reuse, reuse], "repeats a reused declaration"),
        ([], [reuse], "does not hold"),
    ]
    for definitions, reused, message in invalid_scopes:
        with pytest.raises(ValueError, match=message):
            TypingScope(path="src/payments", definitions=definitions, reused_definitions=reused)

    with pytest.raises(ValueError, match="cannot import itself"):
        typing_reuse("A", "src/payments/a.py")
    with pytest.raises(ValueError, match="repeats an importing module"):
        typing_reuse("A", "src/payments/use.py", "src/payments/use.py")


def test_future_annotations_cases() -> None:
    subject = import_table(
        {
            "future_case.py": "from __future__ import annotations\n",
            "typing_case.py": "from typing import Annotated as annotations\n",
        }
    )
    default = future_annotations_query(subject, 14)
    older = future_annotations_query(subject, 13)
    facts = subject.frame(ImportBindingRelation.FACTS).select("fact_id", "module")
    values = default.values.collect().join(facts, on="fact_id")

    assert default.findings is not None
    assert default.fix is not None
    assert (
        values.filter(values["module"] == "__future__").item(0, "boolean_value"),
        values.filter(values["module"] == "typing").item(0, "boolean_value"),
        older.values.collect().get_column("boolean_value").sum(),
        default.findings.rows.collect().height,
        future_annotations_import.query_fix_safety,
        default.fix.rewrites.collect().get_column("kind").to_list(),
    ) == (True, False, 0, 1, FixSafety.REVIEW, ["remove"])


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
    assert retained_value(nullable, nullable_boolean_annotation) == 1

    named = annotations(
        TypeAnnotation(path="a.py", resolved_names=["typing.Any", "builtins.object"]),
        TypeAnnotation(path="a.py", resolved_names=["domain.ObjectId"]),
    )
    assert (
        retained_value(named, prohibited_annotation),
        retained_value(named, prohibited_annotation, prohibited=["Any"]),
    ) == (2, 1)

    recipe = "Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]"
    constrained = annotations(
        TypeAnnotation(path="a.py", constraint_recipe=recipe),
        TypeAnnotation(path="b.py", constraint_recipe=recipe),
        TypeAnnotation(path="b.py", constraint_recipe=recipe),
        TypeAnnotation(path="c.py", constraint_recipe="Annotated[int, Ge(0)]"),
    )
    assert (
        retained_value(constrained, repeated_annotated_constraint),
        retained_value(constrained, repeated_annotated_constraint, minimum_repetitions=4),
    ) == (1, 0)
    shared = annotations(
        *constrained.annotations,
        TypeAnnotation(path="typings.py", constraint_recipe=recipe),
    )
    assert retained_value(shared, repeated_annotated_constraint) == 0


def test_nullable_boolean_points_to_the_annotation_and_excludes_cli_boundaries() -> None:
    """Nullable Boolean findings retain exact syntax unless a CLI owns the tri-state contract."""
    subject = annotation_table(
        {
            "flags.py": """from fire import Fire

def internal(enabled: bool | None) -> None:
    pass

@app.command
def check(external: bool | None = None) -> None:
    pass
"""
        }
    )
    result = native_query(nullable_boolean_annotation, subject)
    findings = result.findings

    assert integer_total(result) == 1
    assert findings is not None
    rows = findings.rows.collect()
    assert rows.height == 1
    assert rows.item(0, "start_line") == 3
    assert rows.item(0, "message") == "nullable Boolean annotation `bool | None`"


def test_repeated_constraint_groups_the_complete_repository_table() -> None:
    """A recipe split across per-file facts still reaches its repository-wide floor."""
    annotation = "Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]"
    subject = annotation_table(
        {
            "a.py": (
                "from typing import Annotated\n"
                "from pydantic import StringConstraints\n"
                f"first: {annotation}\n"
            ),
            "b.py": (
                "from typing import Annotated\n"
                "from pydantic import StringConstraints\n"
                f"second: {annotation}\n"
                f"third: {annotation}\n"
            ),
        }
    )

    assert integer_total(native_query(repeated_annotated_constraint, subject)) == 1


def test_minimum_python_target_cases() -> None:
    complete = ProjectConfigurationFact(
        key="python target",
        span=_SPAN,
        python_target=PythonTargetConfiguration(
            project_minimum_minor=14,
            configured_tools=["ruff", "ty"],
            tool_target_minors={"ruff": 14, "ty": 14},
            per_file_target_minors=[14],
        ),
    )
    assert retained_value(complete, minimum_python_declaration) == 0
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
    assert retained_value(inconsistent, minimum_python_declaration) == 3
    assert (
        retained_value(
            complete.model_copy(update={"python_target": None}),
            minimum_python_declaration,
        )
        == 1
    )
    with pytest.raises(ValueError, match="Unsupported minimum Python version"):
        retained_query(complete, minimum_python_declaration, minimum_version="latest")


def test_typing_call_cases() -> None:
    """A call stands in for typing twice over, once as a repeated cast and once as a conversion.

    The cast pattern counts one accessor cast the same way in enough files to be worth typing at
    the source, whatever typing module spelled it, and the conversion counts only where the
    argument already resolves to `bool` and the builtin name was not shadowed.
    """
    casts = call_table(
        {
            "a.py": """import table
from typing import cast

def first(key):
    value = cast(Type, table.get(key))
    return str(value)
""",
            "b.py": """import table
from typing_extensions import cast

def second(key):
    return cast(Type, table.get(key))
""",
            "c.py": """import table
from typing import cast

def third(key):
    return cast(Type, table.get(key))
""",
        }
    )
    repeated, isolated = (
        native_query(repeated_cast_patterns, cast("Table[Fact]", casts)),
        native_query(
            repeated_cast_patterns,
            cast("Table[Fact]", casts),
            minimum_repetitions=4,
        ),
    )
    assert repeated.findings is not None
    assert (
        integer_total(repeated),
        (repeated_findings := repeated.findings.rows.collect()).height,
        repeated_findings.item(0, "path"),
        "cast to `Type` from `table.get` repeats 3 times across 3 files"
        in repeated_findings.item(0, "message"),
    ) == (3, 1, "a.py", True)
    assert isolated.findings is not None
    assert (integer_total(isolated), isolated.findings.rows.collect().is_empty()) == (0, True)

    conversions = call_table(
        {
            "conversions.py": """def convert(items):
    first = bool(True)
    second = bool(items)
    return first, second


def shadowed(x: bool):
    def bool(value):
        return value
    return bool(x)
"""
        }
    )
    converted = native_query(redundant_boolean_conversion, cast("Table[Fact]", conversions))
    assert converted.fix is not None
    assert (
        integer_total(converted),
        converted.fix.rewrites.collect().get_column("kind").to_list(),
    ) == (1, ["unwrap"])
