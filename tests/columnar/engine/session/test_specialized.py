import json
from typing import TYPE_CHECKING

import polars as pl
import pytest

from mcmr.execution.queries import ModelQuery
from mcmr.facts import CallFact, ClassFact, FunctionFact
from mcmr.table import (
    AnalysisSession,
    CallRelation,
    ClassRelation,
    FunctionRelation,
    Table,
)

from .support import contextual_repository, generic_model_candidates, repository

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize("family", [FunctionFact, ClassFact])
def test_specialized_contextual_family_does_not_request_a_generic_mirror(
    tmp_path: Path,
    family: type[ClassFact | FunctionFact],
) -> None:
    session = AnalysisSession(
        repository(tmp_path), suffixes=[".py"], typed_families=[family.__name__]
    )
    table = session.function_tables() if family is FunctionFact else session.class_tables()

    assert table.family is family
    with pytest.raises(RuntimeError, match="not selected or was released"):
        session.session.table(family.__name__)
    assert list(session.table_markers()) == [family.__name__]


def test_specialized_function_candidates_equal_the_former_generic_mirror(
    tmp_path: Path,
) -> None:
    root = contextual_repository(tmp_path)
    table = AnalysisSession(
        root, suffixes=[".py"], typed_families=[FunctionFact.__name__]
    ).function_tables()
    specialized = ModelQuery.candidate_relation(table).collect().sort("fact_order")
    generic = generic_model_candidates(root, FunctionFact)

    assert specialized.drop("subject_json").equals(generic.drop("subject_json"))
    assert [
        json.loads(subject) for subject in specialized.get_column("subject_json").to_list()
    ] == [json.loads(subject) for subject in generic.get_column("subject_json").to_list()]


def test_specialized_class_candidates_address_one_class_each(tmp_path: Path) -> None:
    table = AnalysisSession(
        contextual_repository(tmp_path),
        suffixes=[".py"],
        typed_families=[ClassFact.__name__],
    ).class_tables()
    candidates = ModelQuery.candidate_relation(table).collect().sort("path", "start_line")
    subjects = [json.loads(item) for item in candidates.get_column("subject_json").to_list()]
    child = next(subject for subject in subjects if subject["fields"]["name"] == "Child")

    assert (
        candidates.height,
        all(candidate.startswith("classes:") for candidate in candidates["fact_id"]),
        [subject["fields"]["name"] for subject in subjects],
        [record["name"] for record in child["records"]],
    ) == (
        table.frame(ClassRelation.CLASSES).height,
        True,
        ["MessageContent", "MessageKind", "Base", "Child", "First", "Second"],
        ["build", "create"],
    )


def test_specialized_call_candidates_address_each_call_and_its_nested_values(
    tmp_path: Path,
) -> None:
    (tmp_path / "calls.py").write_text(
        """import logging


def normalize(value):
    return value


def run(value):
    logging.info("value %s", normalize(value), extra={"kind": "sample"})
"""
    )
    table = AnalysisSession(
        tmp_path, suffixes=[".py"], typed_families=[CallFact.__name__]
    ).call_tables()
    candidates = ModelQuery.candidate_relation(table).collect().sort("start_line", "start_column")
    calls = table.frame(CallRelation.CALLS)
    logging_row = candidates.filter(pl.col("qualified_name") == "logging.info").row(0, named=True)
    subject = json.loads(logging_row["subject_json"])

    assert (
        candidates.height,
        logging_row["fact_id"],
        subject["fields"]["qualified_name"],
        any(record["qualified_name"] == "calls.normalize" for record in subject["records"]),
        [value["string_value"] for value in subject["values"]],
    ) == (
        calls.height,
        calls.filter(pl.col("qualified_name") == "logging.info").item(0, "call_id"),
        "logging.info",
        True,
        ["extra"],
    )


def test_specialized_function_candidates_preserve_evidence(tmp_path: Path) -> None:
    table = AnalysisSession(
        repository(tmp_path), suffixes=[".py"], typed_families=[FunctionFact.__name__]
    ).function_tables()
    parent_id = table.frame(FunctionRelation.FUNCTIONS).item(0, "entity_id")
    table = Table(
        family=table.family,
        relation_type=table.relation_type,
        frames={
            **table.frames,
            FunctionRelation.EVIDENCE: pl.DataFrame(
                {
                    "function_id": [parent_id],
                    "ordinal": pl.Series([0], dtype=pl.UInt64),
                    "signal": ["declared contract"],
                    "detail": ["the source states the intent"],
                    "source": ["sample.py:1"],
                    "confidence": [0.875],
                }
            ),
        },
    )
    candidate = ModelQuery.candidate_relation(table).collect().row(0, named=True)
    subject = json.loads(candidate["subject_json"])

    assert (
        candidate["evidence"],
        subject["fields"]["evidence.length"],
        [record["signal"] for record in subject["records"] if record["signal"]],
    ) == (
        [
            {
                "signal": "declared contract",
                "detail": "the source states the intent",
                "source": "sample.py:1",
                "confidence": 0.875,
            }
        ],
        1,
        ["declared contract"],
    )


def test_specialized_class_candidates_share_module_evidence(tmp_path: Path) -> None:
    table = AnalysisSession(
        contextual_repository(tmp_path),
        suffixes=[".py"],
        typed_families=[ClassFact.__name__],
    ).class_tables()
    parent_id = table.frame(ClassRelation.CLASSES).item(0, "fact_id")
    table = Table(
        family=table.family,
        relation_type=table.relation_type,
        frames={
            **table.frames,
            ClassRelation.EVIDENCE: pl.DataFrame(
                {
                    "fact_id": [parent_id],
                    "ordinal": pl.Series([0], dtype=pl.UInt64),
                    "signal": ["declared contract"],
                    "detail": ["the source states the intent"],
                    "source": ["domain.py:1"],
                    "confidence": [0.875],
                }
            ),
        },
    )
    candidates = ModelQuery.candidate_relation(table).collect()
    expected = [
        {
            "signal": "declared contract",
            "detail": "the source states the intent",
            "source": "domain.py:1",
            "confidence": 0.875,
        }
    ]

    assert candidates.filter(pl.col("path") == "domain.py").height == 4
    assert all(
        evidence == expected
        for evidence in candidates.filter(pl.col("path") == "domain.py")["evidence"].to_list()
    )


def test_empty_suffix_selection_keeps_native_discovery_defaults(tmp_path: Path) -> None:
    (tmp_path / "subject.py").write_text("def answer() -> int:\n    return 42\n")
    functions = (
        AnalysisSession(tmp_path, suffixes=()).function_tables().frame(FunctionRelation.FUNCTIONS)
    )

    assert (functions.height, functions.get_column("name").to_list()) == (1, ["answer"])


def test_one_session_normalizes_resolved_calls_and_expression_trees(tmp_path: Path) -> None:
    (tmp_path / "calls.py").write_text(
        """import asyncio
import torch

def run(value):
    asyncio.run(work())
    return torch.sqrt(torch.abs(value))
"""
    )
    session = AnalysisSession(tmp_path, suffixes=[".py"], typed_families=("CallFact",))
    tables = session.call_tables()
    calls = tables.frame(CallRelation.CALLS)
    expressions = tables.frame(CallRelation.EXPRESSIONS)
    arguments = expressions.filter(expressions["relation"] == "argument")

    assert (
        tables.frame(CallRelation.FACTS).height,
        bool(tables.frame(CallRelation.FACTS).item(0, "fact_id")),
        calls.get_column("qualified_name").to_list(),
        calls.get_column("ordinal").to_list(),
        arguments.height,
        expressions.filter(expressions["parent_expression_id"].is_not_null()).height,
        arguments.get_column("qualified_name").to_list(),
        tables.frame(CallRelation.MODULE_BINDINGS).get_column("name").to_list(),
        all(
            tables.frame(relation).is_empty()
            for relation in (
                CallRelation.KEYWORDS,
                CallRelation.MAPPING_ENTRIES,
                CallRelation.EVIDENCE,
            )
        ),
        list(session.table_markers()),
        session.stats.fact_count,
    ) == (
        1,
        True,
        ["asyncio.run", "calls::work", "torch.sqrt", "torch.abs"],
        [0, 1, 2, 3],
        4,
        1,
        ["calls::work", "torch.abs", "", ""],
        ["run"],
        True,
        ["CallFact"],
        1,
    )
    with pytest.raises(RuntimeError, match="released"):
        session.call_tables()


def test_one_session_normalizes_graph_enriched_classes(tmp_path: Path) -> None:
    (tmp_path / "classes.py").write_text(
        """class Base:
    @classmethod
    def build(cls):
        return cls()

class Child(Base):
    pass
"""
    )
    session = AnalysisSession(tmp_path, suffixes=[".py"], typed_families=["ClassFact"])
    tables = session.class_tables()
    classes = tables.frame(ClassRelation.CLASSES)

    assert (
        tables.frame(ClassRelation.FACTS).height,
        bool(tables.frame(ClassRelation.FACTS).item(0, "fact_id")),
        classes.get_column("name").to_list(),
        classes.get_column("descendant_count").to_list(),
        tables.frame(ClassRelation.METHODS).get_column("name").to_list(),
        tables.frame(ClassRelation.DIRECT_BASES).get_column("value").to_list(),
        tables.frame(ClassRelation.DIRECT_SUBCLASSES).get_column("value").to_list(),
        tables.frame(ClassRelation.METHOD_DECORATORS).get_column("value").to_list(),
        all(
            tables.frame(relation).is_empty()
            for relation in (
                ClassRelation.CLASS_DECORATORS,
                ClassRelation.CLASS_KEYWORDS,
                ClassRelation.IMPORTING_MODULES,
                ClassRelation.OWNER_QUALIFIED_CALLS,
                ClassRelation.COUPLED_GROUPS,
                ClassRelation.COUPLED_GROUP_SUFFIXES,
                ClassRelation.MODEL_FILES,
                ClassRelation.PROJECTIONS,
                ClassRelation.PROJECTION_ATTRIBUTES,
                ClassRelation.PROJECTION_OUTPUT_KEYS,
                ClassRelation.EVIDENCE,
            )
        ),
        list(session.table_markers()),
        session.stats.fact_count,
    ) == (
        1,
        True,
        ["Base", "Child"],
        [1, 0],
        ["build"],
        ["Base"],
        ["Child"],
        ["classmethod"],
        True,
        ["ClassFact"],
        1,
    )
    with pytest.raises(RuntimeError, match="released"):
        session.class_tables()
