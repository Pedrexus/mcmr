from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import ClassFact


class ModelFoundation(StrEnum):
    FROZEN_MODEL = auto()
    MODEL = auto()
    FLEX_MODEL = auto()
    FROZEN_FLEX_MODEL = auto()
    PLAIN_CLASS = auto()
    DATACLASS_EXCEPTION = auto()
    UNCERTAIN = auto()


@rule
async def model_foundation(
    subject: ClassFact,
    backend: ClassificationBackend,
) -> ModelFoundation:
    """Recommend a Python foundation for one class.

    Definition
    ----------
    GLiNER2 classifies explicit class requirements against the house model rubric.
    Validated standard data defaults to `patos.FrozenModel`. Mutable standard data
    uses `patos.Model`. Arbitrary external types use `patos.FlexModel` or
    `patos.FrozenFlexModel` according to mutability. Behavior-rich objects remain plain
    classes, while dataclasses require an explicit dependency or measured performance
    exception.

    Evidence
    --------
    The finding retains the model confidence, class name, and source path.

    Exceptions
    ----------
    Framework-owned base classes and external interoperability contracts may constrain
    the available foundation and should be described in the supplied requirements.

    Examples
    --------
    Immutable validated settings select `FrozenModel`. A mutable record holding a Torch
    tensor selects `FlexModel`. A connection pool with lifecycle behavior stays a class.

    References
    ----------
    Cites "patos documentation", base model contracts
    Cites "Pydantic documentation", model concepts
    """
    return await backend.classify(
        subject,
        category=ModelFoundation,
        instructions=(
            "GLiNER2 classifies explicit class requirements against the house model"
            "rubric. Validated standard data defaults to `patos.FrozenModel`. Mutable"
            "standard data uses `patos.Model`. Arbitrary external types use"
            "`patos.FlexModel` or `patos.FrozenFlexModel` according to mutability."
            "Behavior-rich objects remain plain classes, while dataclasses require an"
            "explicit dependency or measured performance exception."
        ),
    )
