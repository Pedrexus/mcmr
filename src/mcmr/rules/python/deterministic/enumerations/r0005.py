from ..... import rule
from .....facts import AttributeAccess, AttributeAccessFact
from .....models import Count, Replace, SourceRewrite

_STANDARD_CONVERSIONS = {"StrEnum": "str", "IntEnum": "int"}


def public_conversion(access: AttributeAccess) -> str:
    """Return the public conversion proven for one enum value read, or an empty name."""
    if access.name != "value":
        return ""
    bases = set(access.receiver_type_bases)
    return next(
        (call for base, call in _STANDARD_CONVERSIONS.items() if base in bases),
        "",
    )


@rule
def prefer_enum_conversion(subject: AttributeAccessFact) -> Count:
    """Prefer public conversions over direct standard `StrEnum` and `IntEnum` values.

    Definition
    ----------
    Report `.value` reads only when local syntax proves that the receiver is a standard-behavior
    `StrEnum` or `IntEnum`. Proof may come from a direct local member, a member lookup, a local
    enum constructor, an unshadowed concrete annotation, or iteration over a known local enum
    class. Recognize direct and aliased imports from the standard `enum` module. Use `str(member)`
    for a `StrEnum` and `int(member)` for an `IntEnum`. Each proven expression receives a safe
    UTF-8 byte edit that replaces the complete access. The value is the number of accesses found.

    Evidence
    --------
    Each finding records the proven enum kind, conversion, source range, and complete replacement.
    Ordinary objects with a `value` attribute and enum types imported from application modules are
    not inferred from spelling. Concrete annotations must name a nonempty local enum class.

    Exceptions
    ----------
    Do not report plain `Enum`, broad base annotations, ambiguous or rebound names, local classes
    with unknown mixins, or classes that define the relevant `__str__` or `__int__` conversion.
    Direct `.value` access remains appropriate when code deliberately needs a representation that
    differs from the enum's public string or integer conversion.

    Examples
    --------
    Bad
    ~~~
    `Color.RED.value`, `status.value` when `status: Status`, and `[item.value for item in Status]`.

    Good
    ~~~~
    `str(Color.RED)`, `int(HttpCode.OK)`, and `record.value` for an ordinary model field.

    References
    ----------
    Cites "The Python Standard Library", `StrEnum`
    https://docs.python.org/3/library/enum.html#enum.StrEnum
    Cites "The Python Standard Library", `IntEnum`
    https://docs.python.org/3/library/enum.html#enum.IntEnum
    Cites "The Python Standard Library", enum
    https://docs.python.org/3/library/enum.html
    """
    return sum(bool(public_conversion(access)) for access in subject.accesses)


@prefer_enum_conversion.fix(is_default=True)
def use_public_conversion(subject: AttributeAccessFact) -> list[SourceRewrite]:
    """Convert each proven enum value read through the enum's own public conversion."""
    return [
        Replace(target=access.node, source=f"{conversion}({access.receiver_text})")
        for access in subject.accesses
        if access.node is not None and (conversion := public_conversion(access))
    ]
