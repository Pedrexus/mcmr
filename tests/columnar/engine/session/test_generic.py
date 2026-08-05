import sys
from typing import TYPE_CHECKING

import polars as pl
import pytest

from mcmr.facts import (
    AttributeAccessFact,
    CallFact,
    Enum,
    ModuleFact,
    StringExpressionFact,
)
from mcmr.kernel_tables import AnalysisSession as NativeAnalysisSession
from mcmr.plugins import Table
from mcmr.query import RuleQuery, scalar_row_value, table_schema
from mcmr.rules.python import redundant_enum_value
from mcmr.table import AnalysisSession, CallRelation, FunctionRelation, GenericRelation

from .support import direct_generic_repository, repository

if TYPE_CHECKING:
    from collections.abc import Callable
    from enum import StrEnum
    from pathlib import Path


def test_table_indexes_exact_family_relations_without_copying_frames() -> None:
    def rejected(
        error: type[Exception],
        message: str,
        operation: Callable[[], Table[CallFact] | pl.DataFrame],
    ) -> None:
        with pytest.raises(error, match=message):
            operation()

    frame = pl.DataFrame({"value": [1], "language": ["python"]})
    frames: dict[StrEnum, pl.DataFrame] = {relation: frame for relation in CallRelation}
    table = Table[CallFact](family=CallFact, relation_type=CallRelation, frames=frames)

    assert table.frame(CallRelation.CALLS) is frame
    assert table.lazy(CallRelation.CALLS).collect().equals(frame)
    rejected(
        TypeError,
        "does not name a CallFact table relation",
        lambda: table.frame(FunctionRelation.FUNCTIONS),
    )
    rejected(
        TypeError,
        "has no language identity",
        lambda: Table[CallFact](
            family=CallFact,
            relation_type=CallRelation,
            frames={relation: pl.DataFrame({"value": [1]}) for relation in CallRelation},
        ),
    )
    rejected(
        ValueError,
        r"missing \[evidence\]",
        lambda: Table[CallFact](
            family=CallFact,
            relation_type=CallRelation,
            frames={
                relation: candidate
                for relation, candidate in frames.items()
                if relation is not CallRelation.EVIDENCE
            },
        ),
    )
    rejected(
        TypeError,
        "does not belong to CallFact",
        lambda: Table[CallFact](
            family=CallFact,
            relation_type=CallRelation,
            frames={**frames, FunctionRelation.FUNCTIONS: frame},
        ),
    )


def test_one_session_returns_normalized_function_tables_and_marker(tmp_path: Path) -> None:
    session = AnalysisSession(repository(tmp_path), suffixes=[".py"])
    tables = session.function_tables()
    functions = tables.frame(FunctionRelation.FUNCTIONS)

    assert (
        functions.select("name").to_series().to_list(),
        functions.item(0, "cache_decorator"),
        functions.item(0, "definition_kind"),
        functions.item(0, "definition_path"),
        functions.item(0, "definition_start_line"),
        functions.item(0, "body_expression_id"),
        tables.frame(FunctionRelation.PARAMETERS).select("name").to_series().to_list(),
        tables.frame(FunctionRelation.CONTROLS).item(0, "kind"),
        tables.frame(FunctionRelation.DECORATORS).item(0, "decorator"),
        tables.frame(FunctionRelation.REFERENCES).is_empty(),
        tables.frame(FunctionRelation.TENSOR_ROLES).is_empty(),
        list(session.table_markers()),
        session.stats.file_count,
        session.stats.fact_count,
        session.kernel_stats(17).total_nanoseconds,
    ) == (
        ["choose"],
        "cache",
        "function",
        "sample.py",
        4,
        None,
        ["flag", "value"],
        "conditional",
        "cache",
        True,
        True,
        ["FunctionFact"],
        1,
        1,
        17,
    )
    with pytest.raises(RuntimeError, match="already released"):
        session.function_tables()


def test_table_markers_are_moved_out_of_the_native_session_once(tmp_path: Path) -> None:
    session = AnalysisSession(repository(tmp_path))

    assert list(session.table_markers()) == ["FunctionFact"]
    assert list(session.table_markers()) == []


def test_generic_table_keeps_native_relations_and_one_marker(tmp_path: Path) -> None:
    session = AnalysisSession(repository(tmp_path), suffixes=[".py"], typed_families=[ModuleFact])
    table = session.table(ModuleFact)

    assert (
        table.frame(GenericRelation.FACTS).height,
        table.frame(GenericRelation.RECORDS).height > 0,
        bool(table.frame(GenericRelation.VALUES).schema),
        list(session.table_markers()),
    ) == (1, True, True, ["ModuleFact"])


def test_enum_table_preserves_provider_rows_and_executes_its_rule(tmp_path: Path) -> None:
    """A real repository reaches one typed enum table and its table-wide rule."""
    (tmp_path / "status.py").write_text(
        """from enum import StrEnum

class Status(StrEnum):
    READY = 'ready'
    CUSTOM = 'wire-name'
""",
        encoding="utf-8",
    )
    subject = AnalysisSession(tmp_path, suffixes=[".py"], typed_families=[Enum]).table(Enum)
    enums, members = (
        subject.records("enums").collect(),
        subject.records("enums.members").sort("ordinal").collect(),
    )
    result = redundant_enum_value.invoke_table(subject, settings={}, dependencies={})
    if not isinstance(result, RuleQuery):
        raise TypeError("the deterministic enum rule returned a model query")
    if result.findings is None:
        raise TypeError("the redundant value rule omitted its precise finding")
    assert (
        subject.family,
        subject.frame(GenericRelation.FACTS).get_column("path").to_list(),
        (enums.item(0, "name"), enums.item(0, "kind")),
        members.get_column("name").to_list(),
        members.get_column("explicit_value_string").to_list(),
        members.get_column("standard_auto_value_string").to_list(),
        [scalar_row_value(row) for row in result.values.collect().iter_rows(named=True)],
        result.findings.normalized().rows.collect().height,
    ) == (
        Enum,
        ["status.py", ""],
        ("Status", "str_enum"),
        ["READY", "CUSTOM"],
        ["ready", "wire-name"],
        ["ready", "custom"],
        [True, False],
        1,
    )


def test_generic_schema_is_compiled_only_when_its_table_is_requested(tmp_path: Path) -> None:
    native = NativeAnalysisSession(
        repository(tmp_path),
        [],
        python_standard_library=sorted(sys.stdlib_module_names),
        suffixes=[".py"],
        generic_schemas={"ModuleFact": '{"type":"unsupported"}'},
    )

    assert native.next_table_marker() == "ModuleFact"
    with pytest.raises(RuntimeError, match="unsupported fact table schema type"):
        native.table("ModuleFact")


@pytest.mark.parametrize("family", [AttributeAccessFact, StringExpressionFact])
def test_direct_generic_family_equals_the_schema_normalizer(
    tmp_path: Path,
    family: type[AttributeAccessFact | StringExpressionFact],
) -> None:
    root = direct_generic_repository(tmp_path)
    direct_session = AnalysisSession(root, suffixes=[".py"], typed_families=[family])
    direct = direct_session.table(family)
    generic_session = NativeAnalysisSession(
        root,
        [],
        python_standard_library=sorted(sys.stdlib_module_names),
        suffixes=[".py"],
        generic_schemas={family.__name__: table_schema(family)},
    )
    generic = generic_session.table(family.__name__)
    generic_frames = {
        GenericRelation.FACTS: generic.facts,
        GenericRelation.RECORDS: generic.records,
        GenericRelation.VALUES: generic.values,
    }

    assert list(direct_session.table_markers()) == [family.__name__]
    assert [generic_session.next_table_marker() for _ in range(2)] == [family.__name__, None]
    assert all(
        direct.frame(relation).equals(generic_frames[relation], null_equal=True)
        for relation in GenericRelation
    )
