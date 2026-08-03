from enum import StrEnum, auto

import polars as pl

from ..... import Category, rule
from .....execution import ClassificationBackend
from .....execution.queries import ModelQuery
from .....facts import ClassFact
from .....table import Table


class _ModelFoundation(StrEnum):
    APPROPRIATE = auto()
    USE_FROZEN_MODEL = auto()
    USE_MODEL = auto()
    USE_FLEX_MODEL = auto()
    USE_FROZEN_FLEX_MODEL = auto()
    USE_PLAIN_CLASS = auto()
    DATACLASS_EXCEPTION = auto()
    UNCERTAIN = auto()


@rule(
    "PY-MODE1001",
    policy=Category.outcomes(
        _ModelFoundation,
        good={_ModelFoundation.APPROPRIATE, _ModelFoundation.DATACLASS_EXCEPTION},
        neutral={_ModelFoundation.UNCERTAIN},
    ),
)
def model_foundation(
    subject: Table[ClassFact],
    backend: ClassificationBackend,
) -> ModelQuery[_ModelFoundation]:
    """Recommend a Python foundation for one class.

    Definition
    ----------
    Compare one concrete Python class and its exact source with the house model policy. This pass
    receives only dataclasses, direct Pydantic foundation bypasses, and state-bearing plain classes
    without ordinary behavior. Declarative state uses `use_frozen_model` unless supplied source
    establishes mutation after construction. Arbitrary external field types use the corresponding
    flex category only when supplied annotations establish them. A dataclass is an exception only
    when supplied interoperability or measured performance evidence requires it. Otherwise
    recommend the matching approved model. Missing requirements are `uncertain`.

    Evidence
    --------
    The finding retains the model confidence, class name, and source path.

    Exceptions
    ----------
    Framework-owned base classes and external interoperability contracts may constrain
    the available foundation and should be described in the supplied requirements.

    Examples
    --------
    An immutable validated settings dataclass selects `use_frozen_model`. A mutable record holding
    a Torch tensor selects `use_flex_model` only when both facts are supplied. A connection pool
    with lifecycle behavior is `appropriate` as a plain class.

    References
    ----------
    Cites "patos documentation", base model contracts
    Cites "Pydantic documentation", model concepts
    """
    return backend.classification(
        subject,
        category=_ModelFoundation,
        instructions=model_foundation.instructions,
    ).where(
        ~pl.col("is_protocol")
        & (
            pl.col("is_dataclass")
            | pl.col("directly_inherits_pydantic_base_model")
            | (
                pl.col("has_instance_fields")
                & ~pl.col("has_ordinary_behavior")
                & ~pl.col("inherits_approved_model_foundation")
                & ~pl.col("is_declarative_model")
            )
        ),
        requires=(
            "is_protocol",
            "is_dataclass",
            "directly_inherits_pydantic_base_model",
            "has_instance_fields",
            "has_ordinary_behavior",
            "inherits_approved_model_foundation",
            "is_declarative_model",
        ),
    )
