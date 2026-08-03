from enum import StrEnum, auto

from ...... import Category, rule
from ......execution import ClassificationBackend
from ......execution.queries import ModelQuery
from ......facts import ChangeFact
from ......table import Table


class _ChangeLocality(StrEnum):
    LOCALIZED = auto()
    SCATTERED = auto()
    INTENTIONAL_PROTOCOL_CHANGE = auto()
    TRANSIENT = auto()
    UNCERTAIN = auto()


@rule(
    "ALL-ARCH1005",
    policy=Category.outcomes(
        _ChangeLocality,
        good={_ChangeLocality.INTENTIONAL_PROTOCOL_CHANGE, _ChangeLocality.LOCALIZED},
        neutral={_ChangeLocality.TRANSIENT, _ChangeLocality.UNCERTAIN},
    ),
)
def change_locality(
    subject: Table[ChangeFact],
    backend: ClassificationBackend,
) -> ModelQuery[_ChangeLocality]:
    """Judge whether representative behavior changes remain architecturally local.

    Definition
    ----------
    Require representative history and an identified behavior boundary. Separately establish
    repeated unrelated edits, necessary public protocol adoption, and bounded transient work.
    One large commit or one cross-file edit cannot establish scattered change.

    Evidence
    --------
    Findings cite compact graph paths, commit or change-set identifiers, the named behavior,
    and the components touched by each representative change.

    Exceptions
    ----------
    Public protocol migrations, generated sources, and migrations with removal plans may spread
    a change intentionally.

    Examples
    --------
    Adding one payment state through six unrelated switches across four packages is `scattered`.
    Updating every generated client after a versioned schema change is an
    `intentional_protocol_change`. A change that stays inside the package owning the behavior is
    `localized`.

    References
    ----------
    Cites "On the Criteria To Be Used in Decomposing Systems into Modules"
    Cites "Your Code as a Crime Scene", temporal coupling
    Cites "A Philosophy of Software Design", information hiding
    """
    return backend.classification(
        subject,
        category=_ChangeLocality,
        instructions=change_locality.instructions,
    )
