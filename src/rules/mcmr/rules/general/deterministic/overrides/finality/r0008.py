import polars as pl

from ...... import rule
from ......facts import OverrideFact
from ......query import CountQuery
from ......table import Table
from ..relations import OverrideTables, count_query


@rule("ALL-OVER0008")
def final_method_overridden(subject: Table[OverrideFact]) -> CountQuery:
    """Count members a base sealed against overriding that a subclass overrode anyway.

    Definition
    ----------
    Read every member a base declares beside the declaration the subclass writes for it, and
    report an override of a member the base marked final. Sealing a member is the author saying
    the rest of the class depends on this exact behavior, so an override is not an extension, it
    is a hole punched through an invariant somebody wrote down on purpose. Whatever the sealed
    member guaranteed, the base still assumes, and the subclass no longer provides.

    The marker and the override are almost never in the same file, so only a resolved inheritance
    chain can put them side by side, which is the whole reason this needs the graph.

    Evidence
    --------
    Each finding names the subclass, the base, the sealed member, and the decorator that sealed
    it. The value is the number of sealed members overridden.

    Exceptions
    ----------
    A subclass that restates the name as data rather than as a callable is judged by the hiding
    rule instead. A project that seals a member through a decorator of its own making rather than
    through `final` is not read, since the graph records the decorator a class wrote and not what
    that decorator means.

    A type checker also reports this, and it is worth reporting twice, because the marker exists
    to be enforced and a project that runs no type checker still deserves the answer.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       class Ledger:
           @final
           def balance(self):
               return sum(self.entries)


       class CachedLedger(Ledger):
           def balance(self):
               return self.total

    Good
    ~~~~
    .. code-block:: python

       class CachedLedger(Ledger):
           def cached_balance(self):
               return self.total

    References
    ----------
    Generalizes Pylint W0239 overridden-final-method
    https://pylint.readthedocs.io/en/stable/user_guide/messages/warning/overridden-final-method.html
    Cites "PEP 591, Adding a Final Qualifier to Typing"
    https://peps.python.org/pep-0591/
    Cites "Effective Java", design and document for inheritance or else prohibit it
    """
    relations = OverrideTables(subject)
    selected = relations.paired_members().filter(
        pl.col("inherited_callable") & pl.col("declared_callable") & pl.col("inherited_final")
    )
    return count_query(relations.counted(selected), "final method overridden")
