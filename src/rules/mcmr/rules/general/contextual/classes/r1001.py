from enum import StrEnum, auto

import polars as pl

from ..... import Category, rule
from .....execution import ClassificationBackend
from .....execution.queries import ModelQuery
from .....facts import OverrideFact
from .....table import Table


class _InheritanceDesign(StrEnum):
    SUBTYPE = auto()
    MIXIN = auto()
    COMPOSITION = auto()
    FRAMEWORK = auto()
    UNCERTAIN = auto()


@rule(
    "ALL-CLAS1001",
    policy=Category.outcomes(
        _InheritanceDesign,
        good={_InheritanceDesign.SUBTYPE, _InheritanceDesign.MIXIN, _InheritanceDesign.FRAMEWORK},
        neutral={_InheritanceDesign.UNCERTAIN},
    ),
)
def inheritance_design(
    subject: Table[OverrideFact],
    backend: ClassificationBackend,
) -> ModelQuery[_InheritanceDesign]:
    """Judge whether inheritance is preferable to composition.

    Definition
    ----------
    Judge one direct inheritance link from its resolved base and derived declarations and their
    exact member source. Accept it as a subtype when the derived class preserves the base role, as
    a focused mixin when the base contributes one narrow reusable role, or as framework
    inheritance only when supplied names, decorators, and source establish that extension point.
    Choose composition when the derived role is orthogonal to the base role and its declarations
    use inherited members as implementation services. That mismatch is sufficient local evidence
    and does not require proof about unseen clients. Use `uncertain` only when a specific missing
    fact could distinguish two otherwise supported categories, and name that fact in the
    reasoning.

    Evidence
    --------
    Findings cite the resolved inheritance link and the declarations that establish the verdict.

    Exceptions
    ----------
    Small protocol mixins and required framework base classes may be appropriate.

    Examples
    --------
    `CsvReport(Report)` is a `subtype` when every client holding a `Report` can be handed one.
    A `SalesReport` inheriting from `DatabaseClient` and calling its inherited `query` helper is
    `composition`, since the derived domain role is not a kind of database client. A small
    `TimestampMixin` contributing one method is a `mixin`, and a base a framework requires is
    `framework`.

    References
    ----------
    Cites "Fluent Python", Inheritance For Better or For Worse
    Cites "Design Patterns", favor object composition over class inheritance
    Cites "Refactoring", Replace Superclass with Delegate
    """
    return backend.classification(
        subject,
        category=_InheritanceDesign,
        instructions=inheritance_design.instructions,
    ).where(
        (pl.col("depth") == 1) & ((pl.col("declared.length") + pl.col("inherited.length")) > 0),
        requires=("depth", "declared.length", "inherited.length"),
    )
