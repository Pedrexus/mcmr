import polars as pl
from pydantic import NonNegativeInt

from ...... import rule
from ......facts import Enum
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import Table


@rule("PY-ENUM0003")
def shared_enums_module_candidate(
    subject: Table[Enum],
    *,
    minimum_definitions: NonNegativeInt = 3,
    minimum_imported_definitions: NonNegativeInt = 2,
    minimum_cross_module_imports: NonNegativeInt = 3,
    preferred_modules: tuple[str, ...] = ("enums.py", "enums"),
) -> CountQuery:
    """Recommend the narrowest shared `enums.py` for reused enum classes.

    Definition
    ----------
    Detect top-level classes with a configured direct enum base and resolve project-relative and
    absolute `from` imports. Derive one proposed location per reused enum from the longest common
    package of its defining and importing modules. Group enums that independently resolve to the
    same destination, then emit a finding when that destination reaches all configured minima for
    in-scope definitions, reused definitions, and cross-module import occurrences. The value is
    the total enum count.

    Evidence
    --------
    Each finding reports in-scope enums, reused enums, import occurrences, defining modules, the
    proposed dotted module, and exact declaration and import locations. Unrelated enum groups are
    never collapsed merely because the project contains many enums. The value is the total number
    of enums in every scope that reaches all three floors.

    Exceptions
    ----------
    Keep a domain enum beside its sole owner when moving it weakens cohesion or creates a cycle.
    Rule-specific categories and enums that are never imported do not justify centralization. A
    global `enums.py` should not become a dumping ground. A dedicated `enums` package with one enum
    per module is already a preferred shared location. Projects can configure another module,
    package, or framework-specific enum base. `minimum_definitions`,
    `minimum_imported_definitions`, and `minimum_cross_module_imports` are the three floors a
    destination has to reach before it is worth proposing, and `preferred_modules` names the
    layouts that already are a shared location, which is why a destination ending in one of them is
    never reported.

    Examples
    --------
    Enums reused only under `shop.orders` suggest `shop.orders.enums`. One enum imported across
    `shop.orders` and `shop.billing` contributes to `shop.enums`, but unrelated package-local enums
    remain separate. Several local enums with no imports are counted but produce no finding.

    References
    ----------
    Cites "The Python Standard Library", `enum`
    https://docs.python.org/3/library/enum.html
    Cites "Fluent Python", chapter 7
    """
    relations = subject
    preferred = (
        pl.any_horizontal(
            *(pl.col("destination").str.ends_with(module) for module in preferred_modules)
        )
        if preferred_modules
        else pl.lit(False)
    )
    selected = relations.records("scopes").filter(
        (pl.col("enum_count") >= minimum_definitions)
        & (pl.col("reused_enum_count") >= minimum_imported_definitions)
        & (pl.col("cross_module_import_count") >= minimum_cross_module_imports)
        & ~preferred
    )
    facts = relations.counted(selected, pl.col("enum_count"))
    return RuleQuery.integer(
        facts,
        pl.col("value"),
        findings=FindingQuery.precise_integer(
            facts,
            pl.col("value"),
            "shared enums module candidate",
            evidence=pl.col("evidence"),
        ),
    )
