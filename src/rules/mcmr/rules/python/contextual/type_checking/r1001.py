from collections.abc import Sequence
from enum import StrEnum, auto

import polars as pl
from pydantic import NonNegativeInt

from ..... import Category, rule
from .....execution import ClassificationBackend
from .....execution.queries import ModelQuery
from .....facts import SymbolFact
from .....table import GenericRelation, Table
from ...deterministic.symbol_relations import SymbolRelations


class _TypingPlacement(StrEnum):
    MOVE_TO_SHARED_MODULE = auto()
    KEEP_WITH_OWNER = auto()
    UNCERTAIN = auto()


@rule(
    "PY-TYPE1001",
    policy=Category.outcomes(
        _TypingPlacement,
        good={_TypingPlacement.KEEP_WITH_OWNER},
        neutral={_TypingPlacement.UNCERTAIN},
    ),
)
def shared_typing_placement(
    subject: Table[SymbolFact],
    backend: ClassificationBackend,
    *,
    minimum_definitions: NonNegativeInt = 5,
    minimum_imported_definitions: NonNegativeInt = 3,
    minimum_cross_module_imports: NonNegativeInt = 3,
    preferred_modules: Sequence[str] = ("typings.py",),
) -> ModelQuery[_TypingPlacement]:
    """Decide which reusable typing declarations belong in a shared module.

    Definition
    ----------
    Group resolved aliases, Protocols, TypedDicts, and typing factories at their narrowest common
    directory. Nominate declarations outside a preferred typing module only when the scope reaches
    all three configured reuse floors. Decide to move only when the declaration is a low dependency
    contract shared by that scope. Keep a declaration beside the runtime concept it describes.
    Missing ownership or cycle evidence is uncertain.
    `minimum_definitions`, `minimum_imported_definitions`, and `minimum_cross_module_imports`
    define those floors. `preferred_modules` names destinations that already satisfy the policy.

    Evidence
    --------
    Every candidate carries its name, exact source range, current module, proposed destination,
    importing modules, and all scope reuse counts. One model turn answers for one declaration, so
    unrelated declarations cannot share a verdict.

    Exceptions
    ----------
    Scopes below any configured floor and declarations already in a preferred module never reach
    classification. Domain models, enums, dataclasses, and ordinary runtime classes are not typing
    declarations. A type stays with its owner when moving it would weaken cohesion or make a cycle.

    Examples
    --------
    A generic parsing Protocol imported throughout one package can move to that package's
    `typings.py`. An alias describing the private state of one runtime class stays beside that
    class even when annotations elsewhere mention it.

    References
    ----------
    Cites "Python typing specification", aliases and `NewType`
    https://typing.python.org/en/latest/spec/aliases.html
    Cites "Python typing specification", Protocols
    https://typing.python.org/en/latest/spec/protocol.html
    Cites "Fluent Python", chapter 13
    """
    query = backend.classification(
        subject,
        category=_TypingPlacement,
        instructions=shared_typing_placement.instructions,
    )
    record_columns = set(subject.lazy(GenericRelation.RECORDS).collect_schema().names())
    if "name" not in record_columns:
        return query
    source = SymbolRelations(subject).typing_placements()
    preferred = (
        pl.any_horizontal([pl.col("path").str.ends_with(name) for name in preferred_modules])
        if preferred_modules
        else pl.lit(False)
    )
    destination = (
        pl.when(pl.col("scope_path") == "")
        .then(pl.lit("typings.py"))
        .otherwise(pl.concat_str("scope_path", pl.lit("/typings.py")))
    )
    candidates = source.filter(
        ~preferred
        & (pl.col("definition_count") >= minimum_definitions)
        & (pl.col("reused_definition_count") >= minimum_imported_definitions)
        & (pl.col("cross_module_import_count") >= minimum_cross_module_imports)
    ).with_columns(
        pl.col("record_id").alias("fact_id"),
        destination.alias("proposed_destination"),
    )
    return query.project(
        candidates,
        fields=(
            "name",
            "scope_path",
            "definition_count",
            "reused_definition_count",
            "cross_module_import_count",
            "importing_modules",
            "proposed_destination",
        ),
    ).choice(
        "Place this typing declaration at the boundary its evidence supports",
        (
            "move it to the scoped shared typing module",
            "keep it beside the runtime concept that owns it",
        ),
    )
