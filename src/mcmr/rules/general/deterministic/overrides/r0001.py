from ..... import rule
from .....facts import OverrideFact
from .....models import Count
from .signatures import SignatureChange


@rule
def overriding_method_accepts_different_arguments(subject: OverrideFact) -> Count:
    """Count overriding methods that stopped accepting what the method they replace accepts.

    Definition
    ----------
    Read every member a base declares beside the declaration the subclass writes for it, and
    report an override a caller written against the base can no longer reach. Four changes count.
    A dropped position leaves an argument with nowhere to go. An added position with no default
    demands one nobody knew to pass. A keyword-only parameter that appeared, vanished, or changed
    its name is reached by that name alone, so any of the three deletes it. A `*args` or
    `**kwargs` tail the base offered and the override dropped stops swallowing everything else.

    Inheritance is a promise that an instance of the subclass goes wherever an instance of the
    base goes, and each of these breaks that promise in the one place nobody looks. The call site
    holds a base reference, passes what the base documents, and fails at runtime inside a subclass
    it never named. The base is almost always in another file, so nothing but a resolved
    inheritance chain finds the declaration this one replaces.

    Evidence
    --------
    Each finding names the subclass, the base, the member, and both parameter lists in the order
    each side states them, with how every parameter binds. The value counts the ways one override
    departs, so a signature that changed its arguments and also dropped a tail counts twice.

    Exceptions
    ----------
    A name that begins with two underscores is left alone, because Python either rewrites it into
    the class that wrote it or calls it itself, so neither one is part of a substitution anybody
    can perform. A setter is left alone too, since the assigned value reaches it as an argument
    the reader never wrote. A parameter the override adds with a default extends the base rather
    than breaking it, and an override ending in `*args` accepts whatever the base accepted, so
    the positions it stopped naming are the ones that tail stands for.

    A positional-only parameter counts toward the arguments and never toward the names, which is
    exactly what it is. Pylint reads its own tree through a list that leaves positional-only
    parameters out altogether, so an override that drops one is reported here and nowhere there.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       class Reader:
           def load(self, path, encoding):
               return open(path, encoding=encoding).read()


       class CachedReader(Reader):
           def load(self, path):
               return self.cache[path]

    Good
    ~~~~
    .. code-block:: python

       class CachedReader(Reader):
           def load(self, path, encoding):
               return self.cache.get(path) or super().load(path, encoding)

    References
    ----------
    Generalizes Pylint W0221 arguments-differ
    https://pylint.readthedocs.io/en/stable/user_guide/messages/warning/arguments-differ.html
    Cites "A Behavioral Notion of Subtyping", 1994
    Cites "Agile Software Development", the Liskov substitution principle
    """
    return sum(change.differing_arguments for change in SignatureChange.across(subject))
