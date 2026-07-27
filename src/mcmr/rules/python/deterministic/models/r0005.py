from ..... import rule
from .....facts import ClassFact
from .....models import Count


@rule
def manual_model_attribute_projection_count(
    subject: ClassFact, *, minimum_attributes: int = 4
) -> Count:
    """Count structures that manually repeat fields from one model instance.

    Definition
    ----------
    Inspect dictionary literals, sequences of key and value pairs, and keyword calls. Group direct
    attribute reads by their root object when each output key matches the attribute name after
    hyphen normalization. Report a structure that repeats at least `minimum_attributes` distinct
    fields. This is evidence that a Pydantic model, dataclass, or similar typed value already owns
    the schema and should provide the projection.

    Evidence
    --------
    Each finding records the source range, root object, distinct projected attribute count, and
    every repeated attribute. The rule does not require static proof of the root type because the
    matching keys and configured count form the conservative structural signal. The value is the
    number of structures repeating enough fields of one model instance.

    Exceptions
    ----------
    Different output names, computed values involving several attributes, unpacking, positional
    constructor calls, and projections below the threshold are ignored. Explicit projection can
    remain when the target schema intentionally differs, excludes secrets, or requires a stable
    compatibility boundary. Prefer `model_dump` include or exclude controls, a typed conversion
    model, or one named serializer over a second handwritten field list.

    Examples
    --------
    Bad
    ~~~
    A tuple manually lists `("id", definition.id)`, `("summary", definition.summary)`, and many
    more matching fields before rendering them.

    Good
    ~~~~
    `definition.model_dump(mode="json", exclude_defaults=True)` reads the model-owned schema.
    A four-field API payload whose names and transformations deliberately differ remains explicit.

    References
    ----------
    Cites "Pydantic documentation", model serialization
    https://docs.pydantic.dev/latest/concepts/serialization/#modelmodel_dump
    Cites "The Python Standard Library", dataclasses `asdict`
    https://docs.python.org/3/library/dataclasses.html#dataclasses.asdict
    Cites "Refactoring", Data Class and Extract Class
    """
    return sum(
        len(set(projection.attribute_names)) >= minimum_attributes
        and {key.replace("-", "_") for key in projection.output_keys}
        == set(projection.attribute_names)
        for projection in subject.projection_groups
    )
