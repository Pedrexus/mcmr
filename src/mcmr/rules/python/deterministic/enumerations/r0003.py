from ..... import rule
from .....facts import EnumFact
from .....models import Count


@rule
def shared_enums_module_candidate(
    subject: EnumFact,
    *,
    minimum_definitions: int = 3,
    minimum_imported_definitions: int = 2,
    minimum_cross_module_imports: int = 3,
    preferred_modules: tuple[str, ...] = ("enums.py", "enums"),
) -> Count:
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
    return sum(
        scope.enum_count
        for scope in subject.scopes
        if scope.enum_count >= minimum_definitions
        and scope.reused_enum_count >= minimum_imported_definitions
        and scope.cross_module_import_count >= minimum_cross_module_imports
        and not any(scope.destination.endswith(module) for module in preferred_modules)
    )
