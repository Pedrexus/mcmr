from enum import StrEnum, auto

import polars as pl

from ..... import Category, rule
from .....execution import ClassificationBackend
from .....execution.queries import ModelQuery
from .....facts import ClassFact
from .....table import Table


class _PythonInterfaceForm(StrEnum):
    CONCRETE = auto()
    PROTOCOL = auto()
    ABC = auto()
    CALLABLE = auto()
    DUCK = auto()
    UNCERTAIN = auto()


@rule(
    "PY-INTE1001",
    policy=Category.outcomes(_PythonInterfaceForm, neutral=set(_PythonInterfaceForm)),
)
def python_interface_form(
    subject: Table[ClassFact],
    backend: ClassificationBackend,
) -> ModelQuery[_PythonInterfaceForm]:
    """Recommend the smallest Python interface form that fits actual variation.

    Definition
    ----------
    Compare implementations, callers, static typing, runtime checks, shared behavior, extension
    ownership, and function signatures before choosing a concrete type, protocol, ABC, callable,
    or implicit duck-typed contract. The criteria independently establish implementations, static
    contract need, runtime structure, a single call shape, and local dynamic use.

    Evidence
    --------
    Findings cite implementations, calls, runtime checks, shared methods, and extension needs.

    Exceptions
    ----------
    Framework contracts and public plugin APIs may need stronger runtime structure.

    Examples
    --------
    Several unrelated senders sharing one `send` method is `protocol`. One injected transformation
    passed as a function is `callable`. A hierarchy a registry loads at run time is `abc`, and a
    single implementation nothing else stands in for is `concrete`.

    References
    ----------
    Cites "Fluent Python", Interfaces, Protocols, and ABCs
    Cites "PEP 544, Protocols"
    Cites "The Python Standard Library", abc
    """
    return backend.classification(
        subject,
        category=_PythonInterfaceForm,
        instructions=python_interface_form.instructions,
    ).where(
        (pl.col("methods.length") > 0)
        & (
            (pl.col("direct_subclasses.length") > 0)
            | (pl.col("importing_modules.length") > 0)
            | pl.col("is_protocol")
        )
        & ~pl.col("is_test"),
        requires=(
            "methods.length",
            "direct_subclasses.length",
            "importing_modules.length",
            "is_protocol",
            "is_test",
        ),
    )
