from ..... import rule
from .....facts import ClassFact
from .....models import Count


@rule
def approved_model_foundation(
    subject: ClassFact,
) -> Count:
    """Require direct Pydantic models to use an established approved house base.

    Definition
    ----------
    First establish project policy by finding at least one module anywhere in the repository that
    imports a foundation from `patos` or from a `common.bases` module. Then inspect project-owned
    top-level classes and report direct subclasses of an imported `pydantic.BaseModel` that do not
    also inherit an approved base. Resolve direct imports, module imports, and aliases through the
    bindings each file states. Each bypassing class contributes one to the result.

    Evidence
    --------
    Each finding identifies the direct model class and its source range. Which foundations count
    as approved is the provider's single project-specific input, and it recognizes the two house
    homes for one. The value is the number of classes deriving `pydantic.BaseModel` without an
    approved foundation.

    Exceptions
    ----------
    Abstain when the project has not established a house foundation. Ignore Pydantic dataclasses,
    `RootModel`, dynamic `create_model` calls, unresolved bases, nested classes, and subclasses of
    a project foundation because their Pydantic ancestry is not locally proven. Generated and
    vendored sources are excluded by default.

    Examples
    --------
    Bad
    ~~~
    After `from patos import FrozenModel` establishes the policy, this direct foundation bypasses
    it.

    .. code-block:: python

       from pydantic import BaseModel

       class User(BaseModel):
           name: str

    Good
    ~~~~
    The project-owned foundation makes mutability and validation policy explicit.

    .. code-block:: python

       from patos import FrozenModel

       class User(FrozenModel):
           name: str

    References
    ----------
    Cites "Pydantic documentation", models
    https://docs.pydantic.dev/latest/concepts/models/
    Cites "Pydantic documentation", custom base model guidance
    https://docs.pydantic.dev/latest/concepts/models/#custom-base-classes
    Cites "PEP 8, Style Guide for Python Code", public and internal interfaces
    https://peps.python.org/pep-0008/#public-and-internal-interfaces
    """
    if not subject.has_approved_model_foundation_policy:
        return 0
    return sum(
        item.directly_inherits_pydantic_base_model and not item.inherits_approved_model_foundation
        for item in subject.classes
    )
