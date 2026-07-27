from ..... import rule
from .....facts import ClassFact
from .....models import Count


@rule
def shared_model_file_shape(
    subject: ClassFact,
) -> Count:
    """Require one model-shaped class in each shared `models` package implementation file.

    Definition
    ----------
    Apply only to Python files below a `models` directory and exclude `__init__.py`. Require
    exactly one top-level class deriving a recognized Pydantic, house model, SQL table, or
    decorated dataclass foundation. A directory counts as a shared model package only when some
    file inside it really declares a data model, so a folder of neural networks named the same way
    is left alone. Enum classes belong in `enums`. Local model groups consumed only within one
    feature package may remain together in that feature's `models.py` instead.

    Evidence
    --------
    A finding lists every top-level class and covers the complete file. Empty utility files,
    multiple model classes, ordinary service classes, and enum classes all violate this shared
    package shape. The value is the number of files in the shared package that do not hold exactly
    one model class.

    Exceptions
    ----------
    `models/__init__.py` may export model classes used outside the package. A feature-local
    `enums.py` inside a nested model package remains governed by the enum placement rules. A rule
    family named `models` is not a shared data-model package. A class reaching a foundation only
    through a project-owned intermediate base is not counted, because the base each file names is
    what one parse can settle. Generated schemas and migration snapshots may be excluded by path.

    Examples
    --------
    Bad
    ~~~
    `models/accounts.py` defines `Account`, `Profile`, and `AccountStatus` together.

    Good
    ~~~~
    `models/account.py` defines only the `Account` Pydantic model. A final generic result model
    derived through a project-owned abstract `RuleResult` is also accepted. `models/__init__.py`
    exports public models when outside consumers need the package API.

    References
    ----------
    Cites "Pydantic documentation", models
    https://pydantic.dev/docs/validation/latest/concepts/models/
    Cites "The Python Standard Library", dataclasses
    https://docs.python.org/3/library/dataclasses.html
    Cites "A Philosophy of Software Design", chapters 4 and 5
    """
    return sum(
        not file.is_package_initializer
        and (file.top_level_class_count != 1 or file.model_class_count != 1)
        for file in subject.model_files
    )
