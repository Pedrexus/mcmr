from ..... import rule
from .....facts import TypeAnnotationFact
from .....models import Count


@rule
def repeated_annotated_constraint(
    subject: TypeAnnotationFact,
    *,
    minimum_repetitions: int = 3,
    minimum_files: int = 2,
    preferred_modules: tuple[str, ...] = ("typings.py",),
) -> Count:
    """Find repeated inline constrained annotations that deserve a named type alias.

    Definition
    ----------
    Canonicalize inline `Annotated` field, parameter, and return annotations containing
    Pydantic, functional-validator, or `annotated-types` constraints. Group identical recipes
    across the project. Report a recipe after it reaches both `minimum_repetitions` and
    `minimum_files`, unless it already lives in a configured shared typing module. Metadata that
    is field-specific, including defaults, aliases, titles, descriptions, and discriminators, is
    excluded because Pydantic does not permit it inside a named type alias.

    Evidence
    --------
    Each finding shows the exact annotation recipe, occurrence count, affected file count,
    nearest shared `typings.py` destination, and every matching source location. The result value
    counts all reusable inline constrained annotations, including unique recipes.

    Exceptions
    ----------
    A local recipe stays inline until repetition proves a shared concept. Keep aliases near one
    bounded context when a project-wide alias would couple unrelated domains. Configure another
    filename when the project deliberately owns typing aliases elsewhere. `preferred_modules` names
    the layouts that already are a shared location, so a destination ending in one of them is
    stable rather than reported again.

    Examples
    --------
    Bad
    ~~~
    Repeating `Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]` in three
    fields across two modules produces one finding.

    Good
    ~~~~
    Define `type NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True,
    min_length=1)]` once in the nearest shared `typings.py`, then annotate those fields with
    `NonEmptyText`. One isolated constrained field remains inline.

    References
    ----------
    Cites "Pydantic documentation", validators, reusable annotated pattern
    https://pydantic.dev/docs/validation/latest/concepts/validators/#using-the-annotated-pattern
    Cites "Pydantic documentation", custom types, named PEP 695 aliases
    https://pydantic.dev/docs/validation/latest/concepts/types/#named-type-aliases
    Cites "Python typing specification", type aliases
    https://typing.python.org/en/latest/spec/aliases.html
    """
    recipes = {
        annotation.constraint_recipe
        for annotation in subject.annotations
        if annotation.constraint_recipe
    }
    return sum(
        len(
            [
                annotation
                for annotation in subject.annotations
                if annotation.constraint_recipe == recipe
                and not annotation.is_field_specific_metadata
            ]
        )
        >= minimum_repetitions
        and len(
            {
                annotation.path
                for annotation in subject.annotations
                if annotation.constraint_recipe == recipe
                and not annotation.is_field_specific_metadata
            }
        )
        >= minimum_files
        and not any(
            annotation.path.endswith(module)
            for annotation in subject.annotations
            if annotation.constraint_recipe == recipe
            for module in preferred_modules
        )
        for recipe in recipes
    )
