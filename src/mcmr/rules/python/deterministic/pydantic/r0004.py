from ..... import rule
from .....facts import CallFact, CallSite, LiteralKind
from .....models import Count, Replace, SourceRewrite


def has_mapping_argument(call: CallSite) -> bool:
    """Whether one `model_validate` call carries exactly one literal mapping argument."""
    return (
        call.qualified_name.endswith(".model_validate")
        and len(call.arguments) == 1
        and call.arguments[0].literal_kind is LiteralKind.MAPPING
        and not call.keyword_names
    )


def constructor_keywords(call: CallSite) -> str:
    """Render the mapping entries of one validated call as constructor keywords."""
    entries = call.arguments[0].entries
    return ", ".join(f"{entry.key}={entry.value.text}" for entry in entries)


@rule
def redundant_model_validate(subject: CallFact) -> Count:
    """Find `model_validate` calls that already spell out ordinary constructor fields.

    Definition
    ----------
    Report `Model.model_validate` only when its sole argument is a dictionary literal or a
    keyword-only `dict` call with nonempty identifier keys and no validation options. In this
    shape the code already knows every field and `Model(field=value)` states that intent more
    directly. Keep `model_validate` at boundaries that receive an existing mapping, decoded
    document, ORM object, plugin payload, or caller-selected validation options.

    Evidence
    --------
    Each finding identifies the call and every explicit input key. The rule does not infer model
    schemas, aliases, or data produced at runtime. The value is the number of `model_validate`
    calls carrying one literal mapping.

    Exceptions
    ----------
    Mapping variables, dictionary unpacking, non-identifier aliases, `from_attributes`, strictness,
    context, and other validation options are excluded. A thin `from_table` method may reasonably
    call `cls.model_validate(table)` because the mapping itself is the boundary.

    Examples
    --------
    Bad
    ~~~
    `User.model_validate({"name": name, "age": age})` repeats an ordinary constructor shape.

    Good
    ~~~~
    `User(name=name, age=age)` constructs explicit application values. `User.model_validate(row)`
    validates an existing external mapping and remains appropriate.

    References
    ----------
    Cites "Pydantic documentation", models and model validation methods
    https://pydantic.dev/docs/validation/latest/concepts/models/
    Cites "Pydantic documentation", aliases and mapping validation
    https://pydantic.dev/docs/validation/latest/concepts/alias/
    """
    return sum(has_mapping_argument(call) for call in subject.calls)


@redundant_model_validate.fix(is_default=True)
def use_model_constructor(subject: CallFact) -> list[SourceRewrite]:
    """State the known fields through the model constructor itself."""
    return [
        Replace(target=call.node, source=f"{call.receiver.text}({constructor_keywords(call)})")
        for call in subject.calls
        if call.node is not None and call.receiver is not None and has_mapping_argument(call)
    ]
