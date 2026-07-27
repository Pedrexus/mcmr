from ..... import rule
from .....facts import LiteralGroupFact


@rule
def parallel_enum_metadata(subject: LiteralGroupFact) -> bool:
    """Detect static string dictionaries that mirror one enum.

    Definition
    ----------
    A parallel metadata dictionary has at least two entries, uses members of one locally
    defined enum as every key, and uses string literals as every value. The enum can own
    these descriptions directly and generate the dictionary when an API needs one.

    Evidence
    --------
    Every finding identifies one parallel dictionary expression and its enum class.

    Exceptions
    ----------
    Dynamic handler registries, non-string values, partial runtime overrides, and mappings
    across several enum types remain separate data structures.

    Examples
    --------
    `{Intent.TODO: "Future work", Intent.WHY: "Rationale"}` mirrors static enum
    descriptions. `{Intent.TODO: handle_todo}` remains a behavior registry.

    References
    ----------
    Cites "Refactoring", Parallel Inheritance Hierarchies
    """
    return any(
        metadata.all_keys_resolve_to_enum
        and len(metadata.keys) >= 2
        and len(metadata.keys) == len(metadata.values)
        for metadata in subject.enum_metadata_maps
    )
