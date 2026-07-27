from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import InterfaceFact


class PythonInterfaceForm(StrEnum):
    CONCRETE = auto()
    PROTOCOL = auto()
    ABC = auto()
    CALLABLE = auto()
    DUCK = auto()
    UNCERTAIN = auto()


@rule
async def python_interface_form(
    subject: InterfaceFact,
    backend: ClassificationBackend,
) -> PythonInterfaceForm:
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
    return await backend.classify(
        subject,
        category=PythonInterfaceForm,
        instructions=(
            "Compare implementations, callers, static typing, runtime checks, shared"
            "behavior, extension ownership, and function signatures before choosing a"
            "concrete type, protocol, ABC, callable, or implicit duck-typed contract. The"
            "criteria independently establish implementations, static contract need,"
            "runtime structure, a single call shape, and local dynamic use."
        ),
    )
