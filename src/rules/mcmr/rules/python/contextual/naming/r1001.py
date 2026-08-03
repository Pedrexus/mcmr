from enum import StrEnum, auto

import polars as pl

from ..... import Category, rule
from .....execution import ClassificationBackend
from .....execution.queries import ModelQuery
from .....facts import SymbolFact
from .....table import GenericRelation, Table
from ...deterministic.symbol_relations import SymbolRelations


class _AttributeVisibility(StrEnum):
    PUBLIC = auto()
    JUSTIFIED_NON_PUBLIC = auto()
    JUSTIFIED_NAME_MANGLING = auto()
    DOCUMENTED_DUNDER = auto()
    UNJUSTIFIED_NON_PUBLIC = auto()
    INVALID_DUNDER = auto()
    UNCERTAIN = auto()


@rule(
    "PY-NAMI1001",
    policy=Category.outcomes(
        _AttributeVisibility,
        good={
            _AttributeVisibility.DOCUMENTED_DUNDER,
            _AttributeVisibility.JUSTIFIED_NAME_MANGLING,
            _AttributeVisibility.JUSTIFIED_NON_PUBLIC,
            _AttributeVisibility.PUBLIC,
        },
        neutral={_AttributeVisibility.UNCERTAIN},
    ),
)
def attribute_visibility(
    subject: Table[SymbolFact],
    backend: ClassificationBackend,
) -> ModelQuery[_AttributeVisibility]:
    """Judge whether one Python name should be public or non-public.

    Definition
    ----------
    Public is the project default. One leading underscore is justified only for an
    implementation detail that carries no public compatibility promise. Two leading
    underscores are justified only to prevent accidental subclass name collisions.
    Double-leading-and-trailing names must be documented Python special names.

    Evidence
    --------
    The finding retains the supplied role, usage context, source path, and model confidence.

    Exceptions
    ----------
    Framework contracts, generated code, imported compatibility surfaces, and explicitly
    documented public or subclass APIs may require a particular spelling.

    Examples
    --------
    `cache` is `public` by default. `_cache` needs evidence that callers must not depend on it.
    `__cache` is reserved for preventing accidental subclass collisions.

    References
    ----------
    Cites "The Python Tutorial", section 9.6 on private variables
    Cites "PEP 8, Style Guide for Python Code", naming conventions and designing for inheritance
    """
    query = backend.classification(
        subject,
        category=_AttributeVisibility,
        instructions=attribute_visibility.instructions,
    )
    record_columns = set(subject.lazy(GenericRelation.RECORDS).collect_schema().names())
    if "reference.id" not in record_columns:
        return query
    names = (
        SymbolRelations(subject)
        .symbols()
        .filter(
            pl.col("name").str.starts_with("_")
            & (pl.col("name") != "_")
            & (pl.col("scope") != "local")
            & ~pl.col("path").str.contains(r"(?:^|/)tests?(?:/|$)")
        )
        .with_columns(pl.col("record_id").alias("fact_id"))
    )
    return query.project(
        names,
        fields=(
            "name",
            "scope",
            "is_constant_assignment",
            "returns_boolean",
            "reference_count",
            "reference.declaration.kind",
            "reference.declaration.text",
        ),
    )
