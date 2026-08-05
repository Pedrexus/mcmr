from typing import TYPE_CHECKING

import pytest

from mcmr.contextual.evaluation import ContextualSweep
from mcmr.domain.contracts import RuleContract, RuleSetting
from mcmr.execution import ClassificationBackend
from mcmr.execution.queries import ModelQuery
from mcmr.facts import FunctionFact, ModuleCouplingFact, StringExpressionFact, SymbolFact
from mcmr.plugins import RepositoryTables, Table
from mcmr.rules.general import (
    algorithmic_complexity,
    bounded_work,
    component_balance,
    dependency_boundary_alignment,
    primitive_obsession,
    string_construction_mechanism,
)
from mcmr.rules.python import shared_typing_placement
from mcmr.table import AnalysisSession

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    import polars as pl

from mcmr.plugins import Fact

_RIGHT_SOURCE = "def normalize(value: int) -> int:\n    return abs(value)\n"
_LEFT_SOURCE = """from right.values import normalize

_INTERNAL_LIMIT = 8
DESCRIPTION = (
    "This deliberately long runtime string gives the contextual planner enough "
    "concrete text to judge its construction mechanism."
)

def primitive(code: str, count: int) -> int:
    if code:
        return normalize(count) + len(code)
    return count

def looped(values: list[int]) -> int:
    total = 0
    for value in values:
        total += normalize(value)
    return total
"""


def candidates[Family: Fact](
    contract: RuleContract,
    subject: Table[Family],
    *,
    settings: Mapping[str, RuleSetting] | None = None,
) -> pl.DataFrame:
    """Collect the candidates selected by one contextual projection."""
    query = contract.invoke_table(
        subject,
        settings={} if settings is None else settings,
        dependencies={ClassificationBackend: ClassificationBackend.find("codex")()},
    )
    assert isinstance(query, ModelQuery)
    return query.candidates.collect()


def write_repository(root: Path) -> None:
    """Write evidence for graph, function, string, and symbol projections."""
    left = root / "left"
    right = root / "right"
    left.mkdir()
    right.mkdir()
    (left / "__init__.py").write_text("", encoding="utf-8")
    (right / "__init__.py").write_text("", encoding="utf-8")
    (right / "values.py").write_text(_RIGHT_SOURCE, encoding="utf-8")
    (left / "work.py").write_text(_LEFT_SOURCE, encoding="utf-8")


@pytest.fixture
def repository_tables(tmp_path: Path) -> RepositoryTables:
    """Extract every specialized table from one native analysis session."""
    write_repository(tmp_path)
    families = [ModuleCouplingFact, FunctionFact, StringExpressionFact, SymbolFact]
    session = AnalysisSession(
        tmp_path,
        suffixes=[".py"],
        typed_families=[family for family in families],
    )
    tables = RepositoryTables()
    for family in families:
        tables.add(session.table(family))
    return tables


def test_architecture_projections_group_repository_evidence(
    repository_tables: RepositoryTables,
) -> None:
    coupling = repository_tables[ModuleCouplingFact]
    boundaries = candidates(dependency_boundary_alignment, coupling)
    components = candidates(component_balance, coupling)
    assert boundaries.get_column("fact_id").to_list() == ["boundary:python:left->right"]
    assert components.get_column("fact_id").to_list() == ["component-balance:repository"]


def test_function_projections_select_supported_operations(
    repository_tables: RepositoryTables,
) -> None:
    functions = repository_tables[FunctionFact]
    primitive = candidates(primitive_obsession, functions)
    complexity = candidates(algorithmic_complexity, functions)
    work = candidates(bounded_work, functions)
    assert primitive.get_column("fact_id").to_list() == ["function:left/work.py:9:0:primitive"]
    assert complexity.is_empty()
    assert work.is_empty()


def test_expression_projections_keep_exact_source_sites(
    repository_tables: RepositoryTables,
) -> None:
    strings = repository_tables[StringExpressionFact]
    selected_strings = candidates(string_construction_mechanism, strings)
    assert selected_strings.get_column("path").to_list() == ["left/work.py"]


def test_typing_projection_supports_default_and_empty_destinations(
    repository_tables: RepositoryTables,
) -> None:
    names = repository_tables[SymbolFact]
    candidates(shared_typing_placement, names)
    candidates(shared_typing_placement, names, settings={"preferred_modules": []})


def test_sparse_sweep_tables_keep_the_default_contextual_projection() -> None:
    coupling = ContextualSweep.table(ModuleCouplingFact, "ALL-ARCH1002")
    strings = ContextualSweep.table(StringExpressionFact, "ALL-STRI1001")
    symbols = ContextualSweep.table(SymbolFact, "PY-TYPE1001")

    assert candidates(dependency_boundary_alignment, coupling).height == 1
    assert candidates(string_construction_mechanism, strings).height == 1
    assert candidates(shared_typing_placement, symbols).height == 1
