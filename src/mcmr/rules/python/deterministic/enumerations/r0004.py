from ..... import rule
from .....facts import EnumFact
from .....models import Count


@rule
def shared_enum_file_shape(subject: EnumFact) -> Count:
    """Require one enum class in each shared `enums` package implementation file.

    Definition
    ----------
    Apply only to Python files below an `enums` directory and exclude `__init__.py`. Require
    exactly one top-level class derived from a configured enum foundation. A small group used only
    within one feature package may stay together in that feature's `enums.py`. A shared `enums`
    package is reserved for enums imported across unrelated package branches.

    Evidence
    --------
    A finding lists every top-level class and covers the complete file. Empty utility files,
    multiple enum classes, ordinary classes, and model classes violate the shared package shape.
    The value is the number of files in the shared package that do not hold exactly one enum class.

    Exceptions
    ----------
    `enums/__init__.py` may export enum classes used outside the package. Generated schemas may be
    excluded by path. Projects can extend the configured enum foundations.

    Examples
    --------
    Bad
    ~~~
    `enums/status.py` defines `RunStatus`, `JobStatus`, and a Pydantic `StatusRecord`.

    Good
    ~~~~
    `enums/run_status.py` defines only `RunStatus`. Three tightly related feature enums used only
    by sibling modules may remain in `feature/enums.py` until their import graph justifies a
    package.

    References
    ----------
    Cites "The Python Standard Library", enum
    https://docs.python.org/3/library/enum.html
    Cites "Fluent Python", chapter 7
    Cites "A Philosophy of Software Design", chapters 4 and 5
    """
    return sum(
        not file.is_package_initializer
        and (file.top_level_class_count != 1 or file.enum_class_count != 1)
        for file in subject.files
    )
