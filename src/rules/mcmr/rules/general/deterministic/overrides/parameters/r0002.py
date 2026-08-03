import polars as pl

from ...... import rule
from ......facts import OverrideFact
from ......query import CountQuery
from ......table import Table
from ..relations import OverrideTables, count_query
from ..signatures import SignatureTables


@rule("ALL-OVER0002")
def overriding_method_renames_a_parameter(subject: Table[OverrideFact]) -> CountQuery:
    """Count the positions an overriding method binds under a name the base never used.

    Definition
    ----------
    Read every member a base declares beside the declaration the subclass writes for it, and
    report each position that still lines up while the name on it changed. Every ordinary
    parameter of a Python method is also a keyword, so a rename silently deletes part of the
    interface. A caller written against the base passes `path=` and gets a type error naming an
    argument it never used, and the reader who has to fix it starts at the call rather than at the
    class that moved the name.

    A reordering is the same defect twice over and is counted that way. Swapping two parameters
    renames both positions, every keyword call keeps working, every positional call keeps running,
    and each one now binds the wrong value to the right name. Documentation is the other cost,
    because two names for one thing means two mental models of one thing.

    Evidence
    --------
    Each finding names the subclass, the base, the member, and the parameter list each side
    states. The value is the number of positions that changed name.

    Exceptions
    ----------
    A name that begins with two underscores is left alone, because Python either rewrites it into
    the class that wrote it or calls it itself. A setter is left alone too, since the assigned
    value reaches it as an argument the reader never wrote. A parameter named as a placeholder is
    not a name any caller was ever meant to use, so replacing it is not a rename.

    Once the two parameter lists stop lining up nothing is renamed, because the positions no
    longer correspond and the changed count is the whole of what happened. A positional-only
    parameter is never renamed either, since no caller can name it. A keyword-only parameter is
    reached by its name alone, so changing it deletes one parameter and adds another, which the
    differing-arguments rule reports as a changed set. The receiver of a class method leaves the
    comparison, because the descriptor supplies it and no call site can pass it.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       class Store:
           def save(self, record):
               self.rows.append(record)


       class AuditedStore(Store):
           def save(self, entry):
               self.rows.append(entry)

    Good
    ~~~~
    .. code-block:: python

       class AuditedStore(Store):
           def save(self, record):
               self.log(record)
               super().save(record)

    References
    ----------
    Generalizes Pylint W0237 arguments-renamed
    https://pylint.readthedocs.io/en/stable/user_guide/messages/warning/arguments-renamed.html
    Cites "Clean Code", chapter 2, use intention-revealing names
    Cites "A Behavioral Notion of Subtyping", 1994
    """
    relations = OverrideTables(subject)
    return count_query(
        relations.counted(
            SignatureTables(relations).changes(),
            pl.col("renamed_parameters"),
        ),
        "overriding method renames a parameter",
    )
