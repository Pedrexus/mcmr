from ..... import rule
from .....facts import SymbolFact
from .....models import (
    Finding,
    FixSafety,
    Measurement,
    OccurrenceReport,
    Rename,
    Reported,
    SourceRewrite,
)


@rule
def boolean_predicate_name(
    subject: SymbolFact,
    *,
    prefixes: tuple[str, ...] = ("is_", "has_", "can_", "should_", "supports_"),
) -> OccurrenceReport:
    """Require Boolean symbols to read as predicates.

    Definition
    ----------
    Require attributes, properties, functions, and methods proven to return Boolean values to begin
    with a configured question prefix after removing any visibility prefix. The default prefixes
    are `is_`, `has_`, `can_`, `should_`, and `supports_`.

    Evidence
    --------
    Each finding names the symbol, the exact place it is declared, and how many references a
    rename would have to move with it, which is what says whether the repair is safe. The rename
    itself arrives from the fix this rule already declares rather than from a second statement of
    the same edit. A symbol whose references are incomplete is reported and left unrepaired.

    Exceptions
    ----------
    Exclude local variables, Python special methods, required overrides, and names imposed by an
    external framework or protocol.

    Examples
    --------
    `ready: bool` fails while `is_ready: bool` passes. A required `__contains__` method is excluded
    even though it returns `bool`.

    References
    ----------
    Adapts Pylint C0103 invalid-name
    Cites "PEP 8, Style Guide for Python Code", naming conventions
    Cites "The Python Standard Library", predicate naming conventions
    Cites "Clean Code", meaningful names
    """
    unmarked = [
        symbol
        for symbol in subject.symbols
        if symbol.returns_boolean and not symbol.name.lstrip("_").startswith(prefixes)
    ]
    return Reported(
        value=bool(unmarked),
        findings=tuple(
            Finding(
                message=(
                    f"`{symbol.name}` answers with a Boolean and its name does not say so, since "
                    f"it opens with none of {', '.join(f'`{item}`' for item in prefixes)}"
                ),
                span=symbol.reference.declaration.span if symbol.reference else subject.span,
                measurements=(
                    Measurement(
                        name="references a rename would move",
                        value=len(symbol.reference.references) if symbol.reference else 0,
                    ),
                ),
            )
            for symbol in unmarked
        ),
    )


@boolean_predicate_name.fix(is_default=True, safety=FixSafety.REVIEW)
def rename_boolean_symbol(
    subject: SymbolFact,
    *,
    prefixes: tuple[str, ...] = ("is_", "has_", "can_", "should_", "supports_"),
) -> list[SourceRewrite]:
    """Rename each predicate at its declaration and at every reference bound to it.

    The leading underscores are carried over rather than stripped, because they are how the
    language states visibility and a rename that dropped them would publish the name.
    """
    return [
        Rename(symbol=symbol.reference, name=renamed(symbol.name, prefixes[0]))
        for symbol in subject.symbols
        if symbol.reference is not None
        and symbol.reference.are_references_complete
        and symbol.returns_boolean
        and not symbol.name.lstrip("_").startswith(prefixes)
    ]


def renamed(name: str, prefix: str) -> str:
    """Return the name with the predicate prefix inserted after whatever hides it."""
    bare = name.lstrip("_")
    return f"{name[: len(name) - len(bare)]}{prefix}{bare}"
