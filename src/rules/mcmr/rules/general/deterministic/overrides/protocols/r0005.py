import polars as pl

from ...... import rule
from ......facts import OverrideFact
from ......query import CountQuery
from ......table import Table
from ..relations import OverrideTables, count_query


@rule("ALL-OVER0005")
def abstract_member_left_unimplemented(
    subject: Table[OverrideFact],
    *,
    abstract_bases: set[str] | None = None,
) -> CountQuery:
    """Count promises a base made that the concrete subclass below it never kept.

    Definition
    ----------
    Read every member a base declares that the subclass never declares again, and report one the
    base marked as abstract when the subclass is meant to be instantiated. An abstract member is a
    contract written down, and a concrete class that leaves one open has published a type that
    raises the moment anybody uses the part nobody finished. The failure lands on whoever
    instantiates the class rather than on whoever wrote it, which is the wrong person and usually
    the wrong week.

    A class is read as abstract itself, and left alone, when it names a base such as `ABC` or
    `Protocol` anywhere above it or when it declares an abstract member of its own. Those are the
    two ways a class says it is a step on the way rather than a destination.

    Evidence
    --------
    Each finding names the subclass, the base that declared the promise, and the member left open.
    The value is the number of unkept promises.

    Exceptions
    ----------
    A class naming one of `abstract_bases` anywhere in its inheritance chain is left alone, and a
    project whose own base spells that differently states its own set. A subclass that redeclares
    the name as data has answered the promise, since something is there to find.

    Pylint also treats a body that only raises `NotImplementedError` as abstract, which is a
    convention rather than a declaration and leaves no decorator for a graph to read, so MCMR
    reports a subset of what Pylint reports rather than guessing at bodies. A metaclass passed as
    a keyword makes a class abstract too and leaves no inheritance edge behind, so that spelling
    is not seen either.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       class Encoder:
           @abstractmethod
           def encode(self, value): ...


       class JsonEncoder(Encoder):
           def describe(self):
               return "json"

    Good
    ~~~~
    .. code-block:: python

       class JsonEncoder(Encoder):
           def encode(self, value):
               return json.dumps(value)

    References
    ----------
    Generalizes Pylint W0223 abstract-method
    https://pylint.readthedocs.io/en/stable/user_guide/messages/warning/abstract-method.html
    Cites "PEP 3119, Introducing Abstract Base Classes"
    https://peps.python.org/pep-3119/
    Cites "Design Patterns", the template method pattern
    """
    abstract_bases = {"ABC", "ABCMeta", "Protocol"} if abstract_bases is None else abstract_bases
    relations = OverrideTables(subject)
    declared = relations.members("declared")
    inherited = relations.members("inherited")
    abstract_links = (
        relations.values("ancestor_names")
        .filter(pl.col("string_value").is_in(list(abstract_bases)))
        .select("fact_id", pl.lit(True).alias("has_abstract_base"))
        .unique()
    )
    promised_links = (
        declared.filter(pl.col("is_promised"))
        .select("fact_id", pl.lit(True).alias("has_declared_promise"))
        .unique()
    )
    unanswered = inherited.filter(pl.col("is_promised")).join(
        declared.select("fact_id", "name"),
        on=["fact_id", "name"],
        how="anti",
    )
    counts = unanswered.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("unanswered_count")
    )
    facts = (
        relations.facts()
        .join(counts, on="fact_id", how="left")
        .join(abstract_links, on="fact_id", how="left")
        .join(promised_links, on="fact_id", how="left")
        .with_columns(
            pl.when(
                pl.col("has_abstract_base").fill_null(False)
                | pl.col("has_declared_promise").fill_null(False)
            )
            .then(0)
            .otherwise(pl.col("unanswered_count").fill_null(0))
            .cast(pl.UInt64)
            .alias("value")
        )
    )
    return count_query(facts, "abstract member left unimplemented")
