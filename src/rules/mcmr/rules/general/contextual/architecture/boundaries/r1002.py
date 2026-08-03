from enum import StrEnum, auto

import polars as pl
from pydantic import PositiveInt

from ...... import Category, rule
from ......execution import ClassificationBackend
from ......execution.queries import ModelQuery
from ......facts import ModuleCouplingFact
from ......table import GenericRelation, Table
from ....deterministic.coupling import CouplingRelations


class _DependencyBoundaryAlignment(StrEnum):
    ALIGNED = auto()
    LEAKY = auto()
    INTENTIONAL_BRIDGE = auto()
    UNCERTAIN = auto()


@rule(
    "ALL-ARCH1002",
    policy=Category.outcomes(
        _DependencyBoundaryAlignment,
        good={
            _DependencyBoundaryAlignment.ALIGNED,
            _DependencyBoundaryAlignment.INTENTIONAL_BRIDGE,
        },
        neutral={_DependencyBoundaryAlignment.UNCERTAIN},
    ),
)
def dependency_boundary_alignment(
    subject: Table[ModuleCouplingFact],
    backend: ClassificationBackend,
    *,
    boundary_depth: PositiveInt = 1,
) -> ModelQuery[_DependencyBoundaryAlignment]:
    """Judge whether dependencies honor one identified architectural boundary.

    Definition
    ----------
    Require evidence naming the intended boundary before judging it. Separately establish use
    of public entries, repeated internal bypasses, coordinated changes, and a deliberate bridge
    role. Missing intent produces uncertainty rather than a guessed architecture violation.
    `boundary_depth` selects how many module path segments identify each component.

    Evidence
    --------
    Findings cite the compact graph nodes, declared boundary, consumers, and representative
    changes that establish or contradict the crossing.

    Exceptions
    ----------
    Adapters, facades, gateways, and composition roots may intentionally cross boundaries.

    Examples
    --------
    Three feature packages calling private storage implementation classes behind a repository
    interface are `leaky`. One HTTP adapter translating into that same interface is an
    `intentional_bridge`. Consumers reaching the storage package only through its public entries
    are `aligned`, and a boundary no evidence names at all is `uncertain`.

    References
    ----------
    Cites "Clean Architecture", boundary anatomy
    Cites "Domain-Driven Design", bounded contexts and anticorruption layers
    Cites "Building Evolutionary Architectures", dependency fitness functions
    """
    query = backend.classification(
        subject,
        category=_DependencyBoundaryAlignment,
        instructions=dependency_boundary_alignment.instructions,
    )
    record_columns = set(subject.lazy(GenericRelation.RECORDS).collect_schema().names())
    fact_columns = set(subject.lazy(GenericRelation.FACTS).collect_schema().names())
    if not {"record_id", "module", "afferent_count", "efferent_count"}.issubset(
        record_columns
    ) or not {
        "module",
        "declaration_count",
        "abstract_declaration_count",
        "afferent_count",
        "efferent_count",
    }.issubset(fact_columns):
        return query
    edges = CouplingRelations(subject).dependencies()
    source_component = (
        pl.col("module")
        .str.replace_all("::", ".", literal=True)
        .str.replace_all("/", ".", literal=True)
        .str.split(".")
        .list.slice(0, boundary_depth)
        .list.join(".")
    )
    dependency_component = (
        pl.col("dependency_module")
        .str.replace_all("::", ".", literal=True)
        .str.replace_all("/", ".", literal=True)
        .str.split(".")
        .list.slice(0, boundary_depth)
        .list.join(".")
    )
    crossings = (
        edges.with_columns(
            source_component.alias("source_component"),
            dependency_component.alias("dependency_component"),
        )
        .filter(
            (pl.col("source_component") != "")
            & (pl.col("dependency_component") != "")
            & (pl.col("source_component") != pl.col("dependency_component"))
        )
        .group_by("source_component", "dependency_component", "language", maintain_order=True)
        .agg(
            pl.col("fact_order").min(),
            pl.col("path").first(),
            pl.col("start_line").first(),
            pl.col("start_column").first(),
            pl.col("end_line").first(),
            pl.col("end_column").first(),
            pl.len().cast(pl.UInt64).alias("crossing_count"),
            pl.struct(
                "module",
                "dependency_module",
                "afferent_count",
                "instability",
                "dependency_instability",
            ).alias("crossings"),
        )
        .with_columns(
            pl.concat_str(
                pl.lit("boundary:"),
                "language",
                pl.lit(":"),
                "source_component",
                pl.lit("->"),
                "dependency_component",
            ).alias("fact_id")
        )
    )
    return query.project(
        crossings,
        fields=(
            "source_component",
            "dependency_component",
            "crossing_count",
            "crossings",
        ),
    )
