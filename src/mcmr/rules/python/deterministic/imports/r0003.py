from ..... import rule
from .....facts import ImportBindingFact
from .....models import (
    Finding,
    FixSafety,
    Measurement,
    OccurrenceReport,
    Remove,
    Reported,
    SourceRewrite,
)


@rule
def unused_import(subject: ImportBindingFact) -> OccurrenceReport:
    """Report an unused import binding.

    Definition
    ----------
    Report one resolved import binding that nothing in its own module reads. A read is counted
    wherever the interpreter would perform one, so a name tested by an `elif`, named as the type
    an `except` catches, matched by a `case`, deleted, used as a decorator, or spelled inside a
    string in a type expression is read exactly as much as a name a call passes.

    Three statements are never judged. A `__future__` import is a compiler directive that binds
    nothing a reader was ever meant to use. A wildcard import binds names this reader cannot
    enumerate, so its disuse is unprovable rather than proven. An import written inside a `try`
    that states what to do when an import fails is there for whether it succeeds.

    Evidence
    --------
    The finding names the binding, the module it came from, and the exact line that states it,
    beside how many references resolved to it, which is the zero the rule turned on. The removal
    arrives from the fix this rule already declares rather than from a second statement of the
    same edit.

    Exceptions
    ----------
    Keep imports that form an explicit public re-export, register behavior with a framework, or
    intentionally execute a documented module side effect. A name a module lists in `__all__` is
    re-exported however that list is built, and so is a name an import restates as its own alias.

    A string inside a subscript is read as the name it spells, since that is where a forward
    reference lives, so a mapping key matching an import silences this rule for that import.
    Reading it the other way would report a live forward reference and offer to delete it, which
    is the failure worth avoiding.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       import json

    Good
    ~~~~
    .. code-block:: python

       from __future__ import annotations
       from .api import Client as Client
       from .transports import *

       try:
           import h2
       except ImportError:
           raise ImportError("install the http2 extra") from None

    References
    ----------
    Generalizes Pylint W0611 unused-import
    Generalizes Ruff F401 unused-import
    Cites "Pyflakes", unused import analysis
    Cites "The Python Language Reference", the import system
    """
    unused = (
        not (
            subject.has_qualifying_use
            or subject.is_reexported
            or subject.is_type_only
            or subject.has_documented_side_effect
            or subject.is_wildcard
            or subject.module == "__future__"
        )
        and subject.reference_count == 0
    )
    if not unused:
        return Reported(value=False)
    return Reported(
        value=True,
        findings=(
            Finding(
                message=(
                    f"`{subject.name}` is imported from `{subject.module}` and nothing in this "
                    f"file reads it"
                ),
                span=subject.declaration.span if subject.declaration else subject.span,
                measurements=(
                    Measurement(name="references to it", value=subject.reference_count),
                ),
            ),
        ),
    )


@unused_import.fix(is_default=True, safety=FixSafety.REVIEW)
def remove_unused_import(subject: ImportBindingFact) -> list[SourceRewrite]:
    """Delete an import statement whose only binding nothing reads.

    Deletion is the whole repair only where the statement binds this one name and nothing else.
    A statement binding several names would lose the live ones along with the dead one, and a
    package initializer states a public surface its own module never reads, so both are reported
    and left for a reader. What remains is offered for review rather than applied unattended,
    because running an import is what registers a plugin or installs a codec, and no reader of one
    file can prove that this one did not.
    """
    removable = subject.is_sole_binding and not subject.span.path.endswith("__init__.py")
    return [Remove(target=subject.declaration)] if subject.declaration and removable else []
