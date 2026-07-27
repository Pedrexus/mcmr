from ..... import rule
from .....facts import RuntimeTypeCheckFact


@rule
def concrete_isinstance_capability(subject: RuntimeTypeCheckFact) -> bool:
    """Detect concrete runtime checks that stand in for a capability.

    Definition
    ----------
    Find `isinstance` checks against concrete numeric and container built-ins. Infer the
    narrowest standard runtime capability from operations in the immediately guarded block.
    Prefer EAFP when the code can simply perform one operation and handle its documented
    exception. The rule reports candidates and never rewrites them automatically because an
    ABC deliberately accepts more implementations than a concrete built-in.

    Evidence
    --------
    Each finding names the concrete types, inferred ABC or protocol, and source location.

    Exceptions
    ----------
    Exact built-in checks remain valid at JSON, TOML, database, wire-format, C-extension,
    dispatch, and other representation boundaries. `str` and `bool` stay concrete because
    their domain meaning is commonly more specific than their inherited capabilities.

    Examples
    --------
    `isinstance(index, int)` guarding arithmetic returns `true` and prefers `numbers.Integral`. An
    indexed read guarded by `isinstance(items, (list, tuple))` returns `true` and prefers
    `collections.abc.Sequence`, including where the guarded block only iterates or measures.
    `isinstance(name, str)` returns `false`, because `str` stays concrete, and so does a check with
    no guarded operation to infer a capability from.

    References
    ----------
    Cites "Fluent Python", chapter 13, Interfaces, Protocols, and ABCs
    Cites "The Python Standard Library", `collections.abc`
    Cites "The Python Standard Library", `numbers` documentation and PEP 3141
    """
    concrete = {"list", "tuple", "dict", "set", "int", "float", "complex"}
    return any(
        check.concrete_type in concrete and bool(check.guarded_operations)
        for check in subject.checks
    )
