from enum import StrEnum, auto

import polars as pl

from ..... import Category, rule
from .....execution import ClassificationBackend
from .....execution.queries import ModelQuery
from .....facts import ClassFact
from .....table import Table


class _ExtensionDesign(StrEnum):
    EXTENSIBLE = auto()
    RIGID = auto()
    SPECULATIVE = auto()
    INTENTIONALLY_CLOSED = auto()
    UNCERTAIN = auto()


@rule(
    "ALL-DESI1003",
    policy=Category.outcomes(
        _ExtensionDesign,
        good={_ExtensionDesign.EXTENSIBLE, _ExtensionDesign.INTENTIONALLY_CLOSED},
        neutral={_ExtensionDesign.UNCERTAIN},
    ),
)
def extension_design(
    subject: Table[ClassFact],
    backend: ClassificationBackend,
) -> ModelQuery[_ExtensionDesign]:
    """Judge whether an established variation can grow without destabilizing policy.

    Definition
    ----------
    Compare current variants, recent additions, branch or type dispatch, edits to stable policy,
    extension contracts, tests, and added indirection. Open closed design means that a demonstrated
    variation usually grows through new code while stable policy remains unchanged. It does not
    require extension machinery for hypothetical change. The criteria separately establish the
    variation axis, extension contract, edits to stable policy, and a justified closed set.

    Evidence
    --------
    Findings cite the variation axis, peer implementations, change history, edited policy units,
    dispatch sites, extension contracts, and direct alternatives.

    Exceptions
    ----------
    Security boundaries, wire protocols, exhaustive domain states, and intentionally finite models
    may be closed to extension. Framework-owned extension mechanisms may constrain the local shape.

    Examples
    --------
    Adding a fourth payment method as one new strategy behind an existing contract is `extensible`.
    Editing six conditionals across pricing policy for every new customer class is `rigid`. A
    plugin registry around one implementation with no expected peer is `speculative`.

    References
    ----------
    Cites "Agile Software Development", Open Closed Principle
    Cites "Design Principles and Design Patterns", Open Closed Principle
    Cites "Software Engineering at Google", SOLID and Open Closed design
    """
    return backend.classification(
        subject,
        category=_ExtensionDesign,
        instructions=extension_design.instructions,
    ).where(
        (pl.col("methods.length") > 0)
        & (
            (pl.col("direct_subclasses.length") > 0)
            | (pl.col("importing_modules.length") > 0)
            | pl.col("is_exported")
        )
        & ~pl.col("is_test"),
        requires=(
            "methods.length",
            "direct_subclasses.length",
            "importing_modules.length",
            "is_exported",
            "is_test",
        ),
    )
