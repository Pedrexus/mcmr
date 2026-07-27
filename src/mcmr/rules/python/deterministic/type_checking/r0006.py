from ..... import rule
from .....facts import SymbolFact
from .....models import Count


@rule
def shared_typings_module_candidate(
    subject: SymbolFact,
    *,
    minimum_definitions: int = 5,
    minimum_imported_definitions: int = 3,
    minimum_cross_module_imports: int = 3,
    preferred_modules: tuple[str, ...] = ("typings.py",),
) -> Count:
    """Recommend scoped `typings.py` modules when reusable declarations are scattered.

    Definition
    ----------
    Detect PEP 695 aliases, explicit `TypeAlias` assignments, typing factories, Protocols, and
    TypedDicts. Resolve project imports and group each reused declaration at the narrowest
    directory shared by its definition and importers. Apply all three configured minima inside
    each independent scope. Emit a finding only when that scope has enough definitions, distinct
    reused definitions, and cross-module imports, and a reused definition remains outside a
    configured preferred module. Unrelated local packages cannot combine to trigger one global
    recommendation. The value is the total project definition count.

    Evidence
    --------
    Each finding reports its scoped definition count, reused definition count, import count,
    defining-module count, and exact declaration and import locations. The value is the total
    number of declarations in every scope that reaches all three floors.

    Exceptions
    ----------
    Domain models, enums, dataclasses, and ordinary runtime classes are excluded. Keep a type
    beside its owner when moving it would create a cycle or weaken cohesion. A shared typings
    module should contain low-dependency contracts and aliases rather than become a dumping ground.
    Projects may choose another filename through `preferred_modules`. `minimum_definitions`,
    `minimum_imported_definitions`, and `minimum_cross_module_imports` are the three floors a
    destination has to reach before centralizing anything is worth proposing.

    Examples
    --------
    Six aliases and Protocols in `src/payments`, with three imported four times by sibling
    modules, recommend `src/payments/typings.py`. Two aliases reused only inside `src/registry`
    and one unrelated alias inside `src/parsing` do not combine to reach the default threshold.
    Definitions already in the scoped `typings.py` are accepted.

    References
    ----------
    Cites "Python typing specification", type aliases and `NewType`
    https://typing.python.org/en/latest/spec/aliases.html
    Cites "Python typing specification", Protocols
    https://typing.python.org/en/latest/spec/protocol.html
    Cites "Fluent Python", chapter 13
    """
    return sum(
        len(scope.definitions)
        for scope in subject.typing_scopes
        if len(scope.definitions) >= minimum_definitions
        and len(set(scope.reused_definitions)) >= minimum_imported_definitions
        and scope.cross_module_import_count >= minimum_cross_module_imports
        and any(
            not any(path.endswith(module) for module in preferred_modules)
            for path in scope.definitions_outside_preferred_module
        )
    )
