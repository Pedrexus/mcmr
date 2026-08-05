from typing import TYPE_CHECKING, Annotated, cast

import polars as pl
import pytest

from mcmr import rule
from mcmr.domain.contracts import FixSafety, RuleScope, fact_type
from mcmr.facts import (
    AlertDefinition,
    AlertFact,
    Evidence,
    ImportBindingFact,
    NodeRef,
    SourceSpan,
    SymbolRef,
)
from mcmr.plugins import Fact, RepositoryTables, Table, fact_table
from mcmr.query import FindingQuery, FixQuery, RuleQuery
from mcmr.table import FunctionRelation, GenericRelation
from mcmr.table.relations import FactRelations

if TYPE_CHECKING:
    from pathlib import Path


def binding_table(root: Path) -> Table[ImportBindingFact]:
    """Normalize one import binding into its native table."""
    span = SourceSpan(path="example.py", end_column=11)
    binding = ImportBindingFact(
        key="module:json",
        span=span,
        name="json",
        module="json",
        declaration=NodeRef(id="import:json", span=span, kind="import", text="import json"),
    )
    return fact_table(ImportBindingFact, [binding])


def test_rule_remains_typed_and_invokes_one_complete_table(tmp_path: Path) -> None:
    @rule("PY-FIXT0001")
    def unused_import(subject: Table[ImportBindingFact]) -> RuleQuery[bool]:
        frame = subject.facts()
        return RuleQuery.boolean(frame, ~pl.col("has_qualifying_use"))

    result = unused_import.invoke_table(
        binding_table(tmp_path),
        settings={},
        dependencies={},
    )

    assert isinstance(result, RuleQuery)
    assert result.values.collect().get_column("boolean_value").to_list() == [True]
    assert unused_import.table_native
    assert unused_import.module == __name__
    assert unused_import.qualname.endswith("unused_import")
    assert not callable(unused_import)
    assert "__call__" not in type(unused_import).__dict__


def test_rule_injects_every_declared_table_once(tmp_path: Path) -> None:
    @rule("PY-FIXT0002")
    def imports_with_alerts(
        imports: Table[ImportBindingFact],
        *,
        alerts: Table[AlertFact],
    ) -> RuleQuery[bool]:
        alert_ids = alerts.facts().select(pl.col("fact_id").alias("alert_id"))
        joined = imports.facts().join(alert_ids, how="cross")
        return RuleQuery.boolean(joined, pl.col("alert_id").is_not_null())

    tables = RepositoryTables()
    tables.add(binding_table(tmp_path))
    tables.add(
        fact_table(
            AlertFact,
            [AlertFact(key="alert:latency", span=SourceSpan(path="operations.yaml"))],
        )
    )
    result = cast(
        "RuleQuery",
        imports_with_alerts.invoke(tables, settings={}, dependencies={}),
    )
    assert (
        imports_with_alerts.tables,
        imports_with_alerts.primary_family,
        result.values.collect().get_column("boolean_value").to_list(),
    ) == (
        [("imports", ImportBindingFact), ("alerts", AlertFact)],
        ImportBindingFact,
        [True],
    )
    with pytest.raises(TypeError, match="requires tables AlertFact, ImportBindingFact"):
        imports_with_alerts.invoke_table(binding_table(tmp_path), settings={}, dependencies={})
    with pytest.raises(ValueError, match="repeated ImportBindingFact"):
        tables.add(binding_table(tmp_path))


def test_table_dependency_metadata_filters_and_caches_language_views() -> None:
    @rule("PY-FIXT0003")
    def python_only(
        subject: Annotated[Table[ImportBindingFact], RuleScope.PYTHON],
    ) -> RuleQuery[bool]:
        return RuleQuery.boolean(subject.lazy(GenericRelation.FACTS), pl.lit(True))

    table = Table(
        ImportBindingFact,
        relation_type=GenericRelation,
        frames={
            GenericRelation.FACTS: pl.DataFrame(
                {
                    "fact_order": [0, 1],
                    "fact_id": ["python", "rust"],
                    "path": ["example.py", "example.rs"],
                    "language": ["python", "rust"],
                }
            ),
            GenericRelation.RECORDS: pl.DataFrame(
                schema={"fact_id": pl.String, "relation": pl.String}
            ),
            GenericRelation.VALUES: pl.DataFrame(
                schema={"fact_id": pl.String, "relation": pl.String}
            ),
        },
    )
    first = table.restricted({"python"})
    second = table.restricted({"python"})
    result = python_only.invoke_table(table, settings={}, dependencies={})
    assert isinstance(result, RuleQuery)

    primary = first.frame(next(iter(first.relation_type)))
    assert (
        first is second,
        primary.get_column("path").unique().to_list(),
        python_only.table_languages,
        fact_type(python_only.hints["subject"]),
        result.values.collect().get_column("fact_id").to_list(),
    ) == (True, ["example.py"], {"subject": {"python"}}, ImportBindingFact, ["python"])


def test_fact_relations_can_sum_selected_rows_per_fact(tmp_path: Path) -> None:
    subject = binding_table(tmp_path)
    relations = FactRelations(subject)
    selected = pl.DataFrame(
        {
            "fact_id": ["module:json", "module:json"],
            "weight": [2, 3],
        }
    ).lazy()

    counted = relations.counted(selected, pl.col("weight")).collect()
    coverage = relations.coverage(selected, pl.col("weight") >= 3).collect()
    empty_values = relations.value_counts("missing").collect()

    assert counted.get_column("value").to_list() == [5]
    assert coverage.get_column("value").to_list() == [50.0]
    assert empty_values.get_column("value").to_list() == [0]


def test_non_table_rules_cannot_enter_table_execution(tmp_path: Path) -> None:
    @rule("PY-FIXT0004")
    def row_unused_import(subject: ImportBindingFact) -> bool:
        return not subject.has_qualifying_use

    with pytest.raises(TypeError, match="is not a table rule"):
        row_unused_import.invoke_table(
            binding_table(tmp_path),
            settings={},
            dependencies={},
        )
    with pytest.raises(TypeError, match="is not a table rule"):
        row_unused_import.invoke(RepositoryTables(), settings={}, dependencies={})
    with pytest.raises(TypeError, match="has no table dependency"):
        _ = row_unused_import.primary_family


def test_table_rejects_a_relation_from_another_family(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="does not name a ImportBindingFact table relation"):
        binding_table(tmp_path).lazy(FunctionRelation.FUNCTIONS)


def test_rule_declares_its_query_owned_fix(tmp_path: Path) -> None:
    @rule("PY-FIXT0005", fix_safety=FixSafety.REVIEW)
    def unused_import(subject: Table[ImportBindingFact]) -> RuleQuery[bool]:
        frame = subject.facts()
        value = ~pl.col("has_qualifying_use")
        fix = FixQuery.build(
            "Delete the unused import.",
            rewrites=FixQuery.empty_rewrites(),
        )
        return RuleQuery.boolean(frame, value, fix=fix)

    result = unused_import.invoke_table(
        binding_table(tmp_path),
        settings={},
        dependencies={},
    )

    assert isinstance(result, RuleQuery)
    assert unused_import.query_fix_safety is FixSafety.REVIEW
    assert result.fix is not None
    assert result.fix.summary == "Delete the unused import."


def test_fact_type_rejects_non_fact_annotations() -> None:
    with pytest.raises(TypeError, match="must be a Fact type"):
        fact_type(str)

    assert fact_type(Table[ImportBindingFact]) is ImportBindingFact


def test_closed_rule_scopes_and_empty_findings_keep_their_transport_contracts() -> None:
    assert RuleScope.C.prefix == "C"
    assert RuleScope.CPP.prefix == "CPP"

    findings = FindingQuery.empty().rows.collect()
    assert findings.is_empty()
    assert findings.columns == [
        "fact_id",
        "finding_order",
        "message",
        "path",
        "start_line",
        "start_column",
        "end_line",
        "end_column",
        "measurement_names",
        "measurement_values",
        "measurement_units",
        "evidence",
        "choice_question",
        "choice_options",
        "provenance_backend",
        "provenance_model",
        "provenance_reasoning_effort",
        "provenance_input_tokens",
        "provenance_cached_input_tokens",
        "provenance_output_tokens",
        "provenance_reasoning_tokens",
    ]


def test_fact_evidence_signals_are_unique() -> None:
    evidence = Evidence(signal="provider", detail="measured", source="fixture")
    with pytest.raises(ValueError, match="evidence"):
        Fact(
            key="fact",
            span=SourceSpan(path="example.py"),
            evidence=[evidence, evidence],
        )


def test_collection_literals_are_isolated_between_model_instances() -> None:
    first = AlertDefinition(name="first")
    second = AlertDefinition(name="second")
    assert first.recent_outcomes == second.recent_outcomes == []
    assert first.recent_outcomes is not second.recent_outcomes

    span = SourceSpan(path="example.py")
    first_symbol = SymbolRef(id="first", name="first", declaration=NodeRef(id="a", span=span))
    second_symbol = SymbolRef(id="second", name="second", declaration=NodeRef(id="b", span=span))
    assert first_symbol.references == second_symbol.references == []
    assert first_symbol.references is not second_symbol.references
