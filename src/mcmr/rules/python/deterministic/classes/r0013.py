from ..... import rule
from .....facts import ClassFact
from .....models import Count


@rule
def duplicate_component_attribute_alias_count(subject: ClassFact) -> Count:
    """Keep retained components as the single source of truth for their attributes.

    Definition
    ----------
    Inspect class constructors and Pydantic `model_post_init` methods. When an owner retains a
    parameter as one field, report other fields assigned directly from attributes of that same
    parameter. `self.document = document` followed by `self.path = document.path` creates two
    access paths for one fact and lets later changes drift. Keep `self.document` and read
    `self.document.path` where needed.

    Evidence
    --------
    Each finding identifies the retained component, copied attribute, alias field, class, and exact
    assignment range. The result is the number of direct forwarded aliases. The value is the number
    of fields assigned directly from an attribute of a retained component.

    Exceptions
    ----------
    Derived values such as `self.name = normalize(document.path.name)` are not direct aliases.
    Extracting a field is accepted when the owner does not retain the source component. Dynamic
    assignments, properties, descriptors, and nested helper scopes are not guessed.

    Examples
    --------
    Bad
    ~~~
    `self.document = document` followed by `self.path = document.path` duplicates composition
    state.

    Good
    ~~~~
    Store only `self.document = document` and use `self.document.path`. If only the path is needed,
    store `self.path = document.path` without retaining the whole document.

    References
    ----------
    Adapts Pylint R0902 too-many-instance-attributes
    Cites "A Philosophy of Software Design", chapter 5, information hiding
    Cites "Pydantic documentation", faux immutability
    https://docs.pydantic.dev/latest/concepts/models/#faux-immutability
    """
    return sum(item.duplicate_component_alias_count for item in subject.classes)
