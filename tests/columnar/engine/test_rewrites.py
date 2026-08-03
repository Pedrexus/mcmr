import polars as pl
import pytest

from mcmr.domain.contracts import ImportRequest, Move, RemoveDirectory, Rename, Unwrap
from mcmr.facts import NodeRef, SourceSpan
from mcmr.query import FixQuery
from mcmr.query.runtime import QueryEvaluations


def evaluations(
    *,
    failures: pl.DataFrame | None = None,
    rewrites: pl.DataFrame | None = None,
) -> QueryEvaluations:
    """Build the materializer with only the relation under test populated."""
    return QueryEvaluations(
        failures=pl.DataFrame() if failures is None else failures,
        findings=pl.DataFrame(),
        fix_rewrites=pl.DataFrame() if rewrites is None else rewrites,
        fix_nodes=FixQuery.empty_nodes().collect(),
        fix_imports=FixQuery.empty_imports().collect(),
    )


def node(identifier: str) -> NodeRef:
    """Build one stable source node for rewrite reconstruction."""
    return NodeRef(
        id=identifier,
        span=SourceSpan(path="subject.py", end_column=len(identifier)),
        kind="identifier",
        text=identifier,
    )


def test_a_failed_table_row_requires_exactly_one_scalar_value() -> None:
    failures = pl.DataFrame(
        {
            "boolean_value": pl.Series([None], dtype=pl.Boolean),
            "integer_value": pl.Series([None], dtype=pl.UInt64),
            "float_value": pl.Series([None], dtype=pl.Float64),
            "category_value": pl.Series([None], dtype=pl.String),
        }
    )

    with pytest.raises(TypeError, match="the rule emitted no scalar value"):
        evaluations(failures=failures).value(0)


def test_move_rewrite_preserves_its_nodes_and_placement() -> None:
    subject = evaluations(
        rewrites=pl.DataFrame({"kind": ["move"], "placement": ["before"], "source": [""]})
    )
    target, anchor = node("target"), node("anchor")

    imports = [ImportRequest(module="models", name="Owner", level=1, type_only=True)]
    move = subject.rewrite(0, {"target": [target], "anchor": [anchor]}, imports)

    assert isinstance(move, Move)
    assert (move.target, move.anchor, str(move.placement)) == (target, anchor, "before")
    assert move.imports == imports


def test_remove_directory_rewrite_preserves_its_repository_path() -> None:
    """A path-only rewrite materializes without inventing a source node."""
    subject = evaluations(
        rewrites=pl.DataFrame({"kind": ["remove-directory"], "source": ["src/empty"]})
    )

    rewrite = subject.rewrite(0, {}, [])

    assert isinstance(rewrite, RemoveDirectory)
    assert rewrite.target == SourceSpan(path="src/empty")


def test_unwrap_rewrite_preserves_the_descendant_to_keep() -> None:
    subject = evaluations(rewrites=pl.DataFrame({"kind": ["unwrap"]}))
    target, keep = node("target"), node("keep")

    unwrap = subject.rewrite(0, {"target": [target], "keep": [keep]}, [])

    assert isinstance(unwrap, Unwrap)
    assert (unwrap.target, unwrap.keep) == (target, keep)


def test_rename_rewrite_preserves_the_resolved_symbol() -> None:
    subject = evaluations(
        rewrites=pl.DataFrame(
            {
                "kind": ["rename"],
                "symbol_id": ["symbol:value"],
                "symbol_name": ["value"],
                "references_complete": [True],
                "name": ["answer"],
            }
        )
    )
    declaration, reference = node("declaration"), node("reference")

    rename = subject.rewrite(
        0,
        {"declaration": [declaration], "reference": [reference]},
        [],
    )

    assert isinstance(rename, Rename)
    assert rename.name == "answer"
    assert rename.symbol.declaration == declaration
    assert rename.symbol.references == [reference]
    assert rename.symbol.are_references_complete


def test_rewrite_materialization_rejects_an_unknown_kind() -> None:
    subject = evaluations(rewrites=pl.DataFrame({"kind": ["transpose"]}))

    with pytest.raises(ValueError, match="unknown table rewrite kind transpose"):
        subject.rewrite(0, {}, [])
