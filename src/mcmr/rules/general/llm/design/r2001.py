from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import DesignStructureFact
from .....models import Choice, Finding, Measurement, Reported, counted


class PrimitiveObsession(StrEnum):
    APPROPRIATE = auto()
    VALUE_OBJECT = auto()
    DOMAIN_MODEL = auto()
    MODELED = auto()
    OVERMODELED = auto()
    UNCERTAIN = auto()


@rule
async def primitive_obsession(
    subject: DesignStructureFact,
    backend: ClassificationBackend,
) -> Reported[PrimitiveObsession]:
    """Classify whether generic values hide repeated domain rules.

    Definition
    ----------
    A primitive is a generic value such as `str`, `int`, or `dict`. Using one is normal. The Fowler
    smell appears only when repeated validation, units, legal states, or operations give that value
    stable domain meaning. One value with repeated rules suggests a value object. Several values
    that change state together suggest a domain model. An existing wrapper is useful only when it
    centralizes those rules. The final category is selected by the explicit decision table, not by
    the judgment backend.

    Evidence
    --------
    The finding names the category the judgment backend reached and the retained claims it
    reached it from, counted and named by signal, so a reader can check the answer against the
    evidence rather than against the model. Those claims cite repeated validation sites,
    operations, parameter groups, state transitions, call boundaries, and any existing wrapper.
    A proposed class is not evidence that an existing abstraction adds knowledge. The repair is
    always a choice here, because a judgment nobody can reproduce is not an edit.

    Exceptions
    ----------
    Local counters, transient parsing values, stable wire formats, and framework-required scalar
    fields can remain generic when their domain rules are not duplicated.

    Examples
    --------
    .. rubric:: Bad example

    Validation for the same monetary concept is repeated at several boundaries.

    .. code-block:: python

       def charge(amount_minor: int, currency: str) -> None:
           if amount_minor < 0 or currency not in SUPPORTED_CURRENCIES:
               raise ValueError("invalid money")

    .. rubric:: Good example

    One immutable value owns the invariant and reusable operation.

    .. code-block:: python

       class Money(FrozenModel):
           amount_minor: int
           currency: Currency

           def add(self, other: Money) -> Money:
               if self.currency is not other.currency:
                   raise ValueError("currency mismatch")
               return Money(
                   amount_minor=self.amount_minor + other.amount_minor,
                   currency=self.currency,
               )

    A loop counter that never crosses its local algorithm remains an `int`.

    References
    ----------
    Cites "Refactoring", Primitive Obsession
    Cites "Domain-Driven Design", Value Objects
    Cites "Refactoring Guru", primitive obsession smell
    """
    verdict = await backend.classify(
        subject,
        category=PrimitiveObsession,
        instructions=(
            "A primitive is a generic value such as ``str``, ``int``, or ``dict``. Using"
            "one is normal. The Fowler smell appears only when repeated validation,"
            "units, legal states, or operations give that value stable domain meaning."
            "One value with repeated rules suggests a value object. Several values that"
            "change state together suggest a domain model. An existing wrapper is useful"
            "only when it centralizes those rules. The final category is selected by the"
            "explicit decision table, not by the judgment backend."
        ),
    )
    signals = ", ".join(f"`{claim.signal}`" for claim in subject.evidence) or "nothing recorded"
    return Reported(
        value=verdict,
        findings=(
            Finding(
                message=(
                    f"the judgment backend read `{subject.key}` as `{verdict}` from "
                    f"{counted(len(subject.evidence), 'retained claim')}, which are {signals}"
                ),
                span=subject.span,
                measurements=(Measurement(name="retained claims", value=len(subject.evidence)),),
                repair=Choice(
                    question=f"check `{verdict}` against the sites those claims name",
                    options=(
                        "model the value where the rules really do repeat",
                        "leave it generic where each site means something different",
                    ),
                ),
            ),
        ),
    )
