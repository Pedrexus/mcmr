from ..... import rule
from .....facts import AttributeAccessFact, ReceiverKind, Visibility
from .....models import Count


@rule
def external_nonpublic_attribute_access_count(
    subject: AttributeAccessFact,
) -> Count:
    """Count nonpublic members accessed outside their declaring type.

    Definition
    ----------
    Inspect every Python attribute expression whose final name begins with one or two underscores.
    Treat a single leading underscore and a double-leading name without a double trailing suffix
    as nonpublic. Inside the innermost lexical class, allow only `self._member`, `cls._member`,
    `CurrentClass._member`, and their double-leading private equivalents. Everywhere else,
    including module functions and other classes, count the access. The rule examines reads,
    writes, calls, annotations, decorators, defaults, and chained receivers alike.

    Evidence
    --------
    Each finding identifies the complete receiver, attribute name, lexical owner if any, and exact
    source location. The value is the total access count. The rule proposes no automatic edit
    because a sound repair may expose a query, command, property, protocol, or other public
    operation rather than merely rename the attribute.

    Exceptions
    ----------
    True double-leading and double-trailing names are Python protocol names and remain allowed,
    including `function.__module__`, `Type.__name__`, `value.__class__`, and special methods.
    Bare names and imports are outside this attribute rule. Subclasses, friends, tests, aliases of
    `self` and chained objects do not gain owner access under the strict default. A direct
    zero-argument `super()._member` access inside a class is valid superclass delegation. Nested
    functions retain their enclosing lexical class, while a nested class establishes a new owner.
    Receiver names are checked syntactically and no type or alias inference is attempted.

    Examples
    --------
    Bad
    ~~~
    At module scope, `service._session.close()` and `service.__token` cross the owner boundary. In
    `Controller`, `service._session` and `self.service._session` do the same. They should call a
    public operation that preserves the owning class invariant.

    Good
    ~~~~
    Within `Service`, `self._session`, `cls._default`, `Service._default`, and `self.__token` are
    owner access. Direct superclass delegation through `super()._session` is also valid.
    `handler.__module__`, `Service.__name__`, and `value.__len__()` are true dunder protocol or
    metadata access and remain valid in every scope.

    References
    ----------
    Generalizes Pylint W0212 protected-access
    Cites "The Python Tutorial", private variables and class-local references
    https://docs.python.org/3/tutorial/classes.html#private-variables
    Cites "PEP 8, Style Guide for Python Code", public and internal interfaces
    https://peps.python.org/pep-0008/#public-and-internal-interfaces
    Cites "The Python Language Reference", special method names
    https://docs.python.org/3/reference/datamodel.html#special-method-names
    """
    return sum(
        access.visibility is not Visibility.PUBLIC
        and not access.is_protocol_name
        and not (
            access.is_inside_owning_class
            and access.receiver_kind in {ReceiverKind.SELF, ReceiverKind.OWNER, ReceiverKind.SUPER}
        )
        for access in subject.accesses
    )
