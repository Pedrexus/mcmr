import polars as pl

from ...... import rule
from ......facts import OverrideFact
from ......query import CountQuery
from ......table import Table
from ..relations import OverrideTables, count_query


@rule("ALL-OVER0010")
def inherited_attribute_hides_a_method(subject: Table[OverrideFact]) -> CountQuery:
    """Count methods a subclass writes under a name an ancestor already binds to data.

    Definition
    ----------
    Read every member a base declares beside the declaration the subclass writes for it, and
    report a name the base binds as data where the subclass writes a method. Python resolves an
    instance attribute before it resolves a method, so the assignment in the ancestor wins and the
    method below is never reached. Nothing about it looks wrong. The method is right there, it is
    covered by nothing, and every call goes to whatever the ancestor stored, which is usually
    `None` and raises somewhere far away.

    Both halves are needed and they never sit together. The assignment is a line inside an
    ancestor's initializer and the method is a definition in another file, so only a resolved
    inheritance chain puts them in the same sentence.

    Evidence
    --------
    Each finding names the subclass, the ancestor that bound the name to data, and the method it
    hides. The value is the number of hidden methods.

    Exceptions
    ----------
    A name Python rewrites into the class that wrote it, spelled with two leading underscores and
    no trailing ones, is left alone, because the two spellings never collide at runtime.

    Only the inherited shape is reported. A class that binds a name to data and defines a method
    under it inside that same class is a local defect a reader can see in one screen, so it
    belongs to a rule about one class rather than to this family, and Pylint reports both under
    one message. A binding a caller makes from outside the class is invisible to any static
    reader, which is the other half of what Pylint's message describes.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       class Task:
           def __init__(self):
               self.run = None


       class ScheduledTask(Task):
           def run(self):
               return self.execute()

    Good
    ~~~~
    .. code-block:: python

       class Task:
           def __init__(self):
               self.runner = None


       class ScheduledTask(Task):
           def run(self):
               return self.execute()

    References
    ----------
    Generalizes Pylint E0202 method-hidden
    https://pylint.readthedocs.io/en/stable/user_guide/messages/error/method-hidden.html
    Cites "The Python Language Reference", the standard type hierarchy and attribute lookup
    https://docs.python.org/3/reference/datamodel.html#invoking-descriptors
    Cites "Fluent Python", attribute handling and the shadowing it allows
    """
    relations = OverrideTables(subject)
    selected = relations.paired_members().filter(
        ~pl.col("inherited_callable")
        & pl.col("declared_callable")
        & ~(pl.col("name").str.starts_with("__") & ~pl.col("name").str.ends_with("__"))
    )
    return count_query(
        relations.counted(selected),
        "inherited attribute hides a method",
    )
