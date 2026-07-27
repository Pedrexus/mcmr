from ..... import rule
from .....facts import PydanticModelFact
from .....models import Count


@rule
def constructor_model_candidate(
    subject: PydanticModelFact,
    *,
    minimum_parameters: int = 3,
    minimum_attributes: int = 3,
    minimum_validations: int = 1,
    minimum_defaults: int = 1,
) -> Count:
    """Recommend a model for constructor-heavy validated data classes.

    Definition
    ----------
    Inspect undecorated classes with no base class and exactly one synchronous `__init__`. Report
    a class when the constructor has at least the configured number of fixed parameters, stores
    those parameters on `self`, validates parameters through an assertion or a conditional
    `ValueError` or `TypeError`, and supplies signature or expression-level defaults. The class
    must otherwise contain only data identity methods. These combined facts distinguish a manual
    data schema from a merely long constructor.

    Evidence
    --------
    Each finding records the class range and exact stored, validated, and defaulted parameter
    names. Measurements expose all four thresholds so a project can tune its recommendation. The
    value is the number of plain classes clearing all four floors together.

    Exceptions
    ----------
    Existing dataclasses, Pydantic and Patos models, inherited framework classes, decorated
    classes, variadic constructors, and classes with behavioral methods are excluded. Constructors
    whose parameter names or annotations explicitly denote clients, services, repositories,
    factories, callbacks, loggers, sessions, transports, or other dependency-injection roles are
    also excluded. Constructors that visibly acquire files, sockets, locks, queues, pools,
    sessions, or connections are resource owners. Classes with `close`, context-manager,
    connection, or execution methods remain behavioral classes rather than data models.
    `minimum_parameters`, `minimum_attributes`, `minimum_validations`, and `minimum_defaults` are
    the four floors a class has to clear together, which is what separates a manual data schema
    from a merely long constructor.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       class AccountInput:
           def __init__(self, name: str, age: int, locale: str = "en") -> None:
               if not name:
                   raise ValueError("name is required")
               self.name = name
               self.age = age
               self.locale = locale

    Good
    ~~~~
    .. code-block:: python

       class AccountInput(FrozenModel):
           name: NonEmptyName
           age: NonNegativeInt
           locale: str = "en"

       class RepositorySession:
           def __init__(self, client: DatabaseClient) -> None:
               self.client = client

           def close(self) -> None:
               self.client.close()

    References
    ----------
    Cites "Pydantic documentation", models
    https://docs.pydantic.dev/latest/concepts/models/
    Cites "Pydantic documentation", fields and constraints
    https://docs.pydantic.dev/latest/concepts/fields/
    Cites "The Python Standard Library", dataclasses
    https://docs.python.org/3/library/dataclasses.html
    Cites "The Python Standard Library", `typing.Protocol`
    https://docs.python.org/3/library/typing.html#typing.Protocol
    """
    return sum(
        model.is_undecorated_plain_class
        and model.synchronous_init_count == 1
        and model.fixed_parameter_count >= minimum_parameters
        and model.stored_parameter_count >= minimum_attributes
        and model.validation_count >= minimum_validations
        and model.default_count >= minimum_defaults
        and model.has_only_data_identity_methods
        for model in subject.models
    )
