import polars as pl
from pydantic import NonNegativeInt

from ...... import rule
from ......facts import PydanticModelFact
from ......query import CountQuery
from ......table import Table
from ..relations import PydanticModelTables, count_query


@rule("PY-PYDA0006")
def constructor_model_candidate(
    subject: Table[PydanticModelFact],
    *,
    minimum_parameters: NonNegativeInt = 3,
    minimum_attributes: NonNegativeInt = 3,
    minimum_validations: NonNegativeInt = 1,
    minimum_defaults: NonNegativeInt = 1,
) -> CountQuery:
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
    tables = PydanticModelTables(subject)
    selected = tables.models().filter(
        pl.col("is_undecorated_plain_class")
        & (pl.col("synchronous_init_count") == 1)
        & (pl.col("fixed_parameter_count") >= minimum_parameters)
        & (pl.col("stored_parameter_count") >= minimum_attributes)
        & (pl.col("validation_count") >= minimum_validations)
        & (pl.col("default_count") >= minimum_defaults)
        & pl.col("has_only_data_identity_methods")
    )
    return count_query(tables.counted(selected), "constructor model candidate")
