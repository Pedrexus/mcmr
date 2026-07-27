from ..... import rule
from .....facts import ClassFact
from .....models import Count


@rule
def pass_through_inheritance_layer_count(
    subject: ClassFact,
    *,
    contract_suffixes: tuple[str, ...] = (
        "Backend",
        "Error",
        "Exception",
        "Mixin",
        "Plugin",
        "Port",
        "Protocol",
        "Provider",
        "Registry",
        "Strategy",
    ),
) -> Count:
    """Count project-owned inheritance layers that add only a name or forwarding frame.

    Definition
    ----------
    Resolve top-level project classes and their direct bases across relative and absolute imports.
    Report an undecorated single-inheritance subclass when its body is only `pass` or an ellipsis,
    or when every body member is an ordinary method that returns the same-named zero-argument
    `super()` method with every positional, variadic, keyword-only, and keyword variadic argument
    unchanged. The existing closed-world single-subclass-base rule owns a pair when the base itself
    can be removed, so this rule abstains from that exact overlap.

    Evidence
    --------
    Each finding identifies the fully qualified project base, layer kind, complete child range, and
    every transparently forwarded method. The result counts shallow child layers rather than base
    classes. The value is the number of shallow child layers rather than the number of bases
    beneath them.

    Exceptions
    ----------
    Decorated classes, class keywords, multiple or external bases, changed arguments, transformed
    returns, asynchronous adapters, descriptors, class methods, and static methods are excluded. A
    name ending in one of the `contract_suffixes` is an intentional type contract, which by default
    covers a protocol, a port, a mixin, a plugin, a strategy, a backend, a provider, a registry,
    and an error. A body holding only a docstring is a class that stated why it exists, so it is
    not a layer nobody meant to add. Keep an otherwise empty class when runtime registration or
    external consumers rely on its identity and disable this preference for that path.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       class JsonSerializer(Serializer):
           pass

       class NamedParser(Parser):
           def parse(self, text: str) -> Node:
               return super().parse(text)

    Good
    ~~~~
    .. code-block:: python

       class JsonSerializer(Serializer):
           def encode(self, value: JsonValue) -> bytes:
               return json.dumps(value).encode()

       class StoragePlugin(Protocol):
           def store(self, payload: bytes) -> None: ...

    References
    ----------
    Generalizes Pylint R0901 too-many-ancestors
    Generalizes Pylint W0246 useless-parent-delegation
    Cites "The Python Language Reference", custom classes
    https://docs.python.org/3/reference/datamodel.html#custom-classes
    Cites "PEP 544, Protocols"
    https://peps.python.org/pep-0544/
    Cites "A Philosophy of Software Design", chapters 4 and 7
    """
    return sum(
        item.scope == "module"
        and len(item.direct_bases) == 1
        and not item.decorators
        and item.is_pass_through_layer
        and not item.base_is_removable_overlap
        and not item.name.endswith(contract_suffixes)
        for item in subject.classes
    )
