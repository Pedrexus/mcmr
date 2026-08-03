from enum import StrEnum, auto

import polars as pl
from pydantic import PositiveInt

from ..... import Category, rule
from .....execution import ClassificationBackend
from .....execution.queries import ModelQuery
from .....facts import ClassFact
from .....table import Table


class _ModelPlacement(StrEnum):
    MOVE_TO_SHARED_BOUNDARY = auto()
    KEEP_WITH_OWNER = auto()
    UNCERTAIN = auto()


@rule(
    "PY-MODE1002",
    policy=Category.outcomes(
        _ModelPlacement,
        good={_ModelPlacement.KEEP_WITH_OWNER},
        neutral={_ModelPlacement.UNCERTAIN},
    ),
)
def shared_model_placement(
    subject: Table[ClassFact],
    backend: ClassificationBackend,
    *,
    minimum_importers: PositiveInt = 2,
) -> ModelQuery[_ModelPlacement]:
    """Decide whether a reused model belongs at its consumers' shared boundary.

    Definition
    ----------
    Nominate declarative top-level models with no ordinary behavior when at least the configured
    number of modules import them and the graph can derive a narrower shared destination. Decide
    to move only when the supplied class source, importing modules, and destination establish that
    the type is a reusable contract rather than a concept owned by its current module. Keep it
    when its current module owns the concept. Missing ownership or cycle evidence is uncertain.
    `minimum_importers` sets the required number of distinct importing modules.

    Evidence
    --------
    Each candidate carries the exact class source, current path, proposed destination, field
    count, importing modules, model ancestry, and graph evidence. The model cites the retained
    claims behind its decision. A failing answer is a placement decision rather than a numeric
    threshold violation.

    Exceptions
    ----------
    Tests, behavioral services, protocols, models with fewer importers, and models already at the
    derived boundary never reach contextual classification. A domain model may remain beside its
    owner. Any unresolved ownership or dependency cycle stays uncertain.

    Examples
    --------
    A generic `Location` record imported by unrelated adapters can move to their shared models
    boundary. An `OrderLine` imported by several order services remains with the order domain when
    that module owns its invariants.

    References
    ----------
    Cites "Pydantic documentation", models
    https://docs.pydantic.dev/latest/concepts/models/
    Cites "A Philosophy of Software Design", chapters 4 and 5
    """
    return (
        backend.classification(
            subject,
            category=_ModelPlacement,
            instructions=shared_model_placement.instructions,
        )
        .where(
            ~pl.col("is_test")
            & pl.col("is_declarative_model")
            & ~pl.col("has_ordinary_behavior")
            & (pl.col("importing_modules.length") >= minimum_importers)
            & (pl.col("proposed_model_destination") != "")
            & (pl.col("path") != pl.col("proposed_model_destination")),
            requires=(
                "is_test",
                "is_declarative_model",
                "has_ordinary_behavior",
                "importing_modules.length",
                "proposed_model_destination",
            ),
        )
        .choice(
            "Place this model at the boundary its evidence supports",
            (
                "move it to the consumers' shared boundary",
                "keep it beside the concept its current module owns",
            ),
        )
    )
