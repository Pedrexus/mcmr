from ..... import rule
from .....facts import ClassFact
from .....models import Count


@rule
def coupled_nested_type_candidate(
    subject: ClassFact,
    *,
    suffixes: tuple[str, ...] = ("Content", "Kind"),
    minimum_types: int = 2,
    minimum_coimports: int = 2,
    maximum_type_lines: int = 30,
    minimum_prefix_length: int = 3,
) -> Count:
    """Find short tightly named classes that may form one nested namespace.

    Definition
    ----------
    Find top-level classes whose names share a prefix and end in configured role suffixes. Require
    at least `minimum_types`, require every class to span no more than `maximum_type_lines`, and
    require at least `minimum_coimports` other modules to import two or more of the classes from
    the same defining module. The default recognizes pairs such as `MessageContent` and
    `MessageKind`. The value is the number of qualifying groups.

    Evidence
    --------
    Findings identify the definitions and every qualifying co-import site. The proposed namespace
    is the shared prefix, producing access such as `Message.Content` and `Message.Kind`. The value
    is the number of qualifying groups rather than the number of classes in them.

    Exceptions
    ----------
    Nested classes do not capture an outer instance and change `__qualname__`, import paths,
    pickling identity, framework discovery, and public APIs. Keep top-level classes when either
    type is independently useful, subclassed externally, registered by qualified name, or easier to
    test separately. A small module namespace can be clearer than a namespace-only class. This is
    an opt-in candidate rule and has no automatic fix. `minimum_prefix_length` keeps a one or two
    character shared prefix from grouping unrelated classes, since a namespace named after two
    letters explains nothing.

    Examples
    --------
    Two twelve-line classes named `EventContent` and `EventKind` that are imported together by
    three modules are reported as an `Event` namespace candidate. A large `EventContent`, a
    `Kind` used alone, or a pair imported together only once is not reported.

    References
    ----------
    Cites "The Python Tutorial", class namespaces and scopes
    https://docs.python.org/3/tutorial/classes.html
    Cites "Google Python Style Guide", nested classes and functions
    https://google.github.io/styleguide/pyguide.html#262-pros
    """
    return sum(
        len(group.prefix) >= minimum_prefix_length
        and frozenset(group.role_suffixes) <= frozenset(suffixes)
        and group.type_count >= minimum_types
        and group.maximum_type_lines <= maximum_type_lines
        and group.coimporting_module_count >= minimum_coimports
        for group in subject.coupled_groups
    )
