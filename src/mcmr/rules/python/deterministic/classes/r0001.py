from ..... import rule
from .....facts import ClassFact


@rule
def explicit_registry_name(
    subject: ClassFact,
    *,
    registry_bases: frozenset[str] = frozenset(
        {"Registry", "Strategy", "Backend", "Provider", "Component"}
    ),
) -> bool:
    """Detect registry classes that override their derivable class key.

    Definition
    ----------
    A class whose direct base is `Registry`, `Strategy`, `Backend`, `Provider`, or
    `Component` should use the registry key derived from its class name. A class-level
    string assignment to `name` duplicates identity and can drift from the class. The shared
    project normalizer derives the snake-case key with `inflection.underscore`.

    Evidence
    --------
    Every finding identifies the explicit class-level `name` assignment and shows the
    snake-case key that the project derives from the class name.

    Exceptions
    ----------
    Keep an override only when a documented external protocol requires a different stable wire key.
    The exception should be explicit because removing it can change configuration. `registry_bases`
    names the bases whose subclasses derive their key from the class name, so a project with its
    own registry foundation states it rather than accepting these five.

    Examples
    --------
    `class JsonBackend(Backend): name = "json_backend"` returns `true`, because the registry
    already derives `json_backend` from the class name. `class JsonBackend(Backend)` with no `name`
    assignment returns `false`. `class JsonBackend(Backend): name = "application/json"` also
    returns `true` and needs an external wire-protocol justification to keep.

    References
    ----------
    Cites "patos documentation", `Registry` auto-derived class names
    Cites "Inflection documentation", underscore
    https://inflection.readthedocs.io/en/latest/#inflection.underscore
    """
    return any(
        registry_bases.intersection(base.rsplit(".", 1)[-1] for base in item.direct_bases)
        and item.has_explicit_registry_name
        for item in subject.classes
    )
