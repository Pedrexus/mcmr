from ..... import rule
from .....facts import OverrideFact
from .....models import Count
from .signatures import SignatureChange


@rule
def overriding_method_demands_an_argument_the_base_defaulted(subject: OverrideFact) -> Count:
    """Count overriding methods that made an optional argument of the base a required one.

    Definition
    ----------
    Read every member a base declares beside the declaration the subclass writes for it, and
    report an override that states the same parameters under the same names while quietly
    withdrawing a default. This is the worst shape a signature change can take, because nothing
    about the two declarations looks different. They have the same length, the same order, and the
    same names, and the only difference is an argument the base said a caller could leave out.

    A call written against the base omits it and works everywhere except where the subclass is
    the object behind the reference, so the defect surfaces on one code path rather than at import
    time. The base is usually in another file, which is why the two declarations are almost never
    read side by side and why only a resolved inheritance chain can put them there.

    Evidence
    --------
    Each finding names the subclass, the base, the member, and the parameter list each side
    states, with the defaults each one writes. The value is the number of overrides that withdrew
    at least one.

    Exceptions
    ----------
    A name that begins with two underscores is left alone, because Python either rewrites it into
    the class that wrote it or calls it itself. A setter is left alone too, since the assigned
    value reaches it as an argument the reader never wrote.

    Any other departure takes the override out of this rule and into one of the other two, so an
    override that also changed a name or a count is reported once as that instead. An override
    ending in `*args` is left alone, because the tail keeps accepting the call that relied on the
    default. A keyword-only default is not counted either, since withdrawing one changes the set
    of arguments a caller must name and the differing-arguments rule owns that.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       class Client:
           def send(self, payload, timeout=30):
               return self.transport.write(payload, timeout)


       class RetryingClient(Client):
           def send(self, payload, timeout):
               return self.retry(super().send, payload, timeout)

    Good
    ~~~~
    .. code-block:: python

       class RetryingClient(Client):
           def send(self, payload, timeout=30):
               return self.retry(super().send, payload, timeout)

    References
    ----------
    Generalizes Pylint W0222 signature-differs
    https://pylint.readthedocs.io/en/stable/user_guide/messages/warning/signature-differs.html
    Cites "A Behavioral Notion of Subtyping", 1994
    Cites "Working Effectively with Legacy Code", chapter 22, seams and signatures
    """
    return sum(
        change.required_what_the_base_defaulted for change in SignatureChange.across(subject)
    )
