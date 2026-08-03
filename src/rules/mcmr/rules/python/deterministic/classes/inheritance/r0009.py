import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import ClassFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import ClassRelation, Table


@rule("PY-CLAS0005")
def artificial_single_subclass_base_count(
    subject: Table[ClassFact],
) -> CountQuery:
    """Count concrete project bases that exist only for one closed-world subclass.

    Definition
    ----------
    Build a project-owned inheritance and import graph over the selected sources. Report a
    top-level base only when it has exactly one direct subclass and no other descendants, neither
    class has decorators or class keywords, the base has no parent except `object`, and the base
    is never instantiated. The base must be absent from `__all__` and package re-exports. Its sole
    cross-module import and every cross-module reference must belong to the subclass declaration.

    Evidence
    --------
    Each finding names the qualified base and subclass, records the subclass and import counts, and
    locates the complete base definition. The proof is deliberately closed-world and covers only
    the configured source snapshot. The value is the number of bases that exist only for their one
    subclass.

    Exceptions
    ----------
    Abstract methods, stubs, Protocols, exceptions, Pydantic and Patos models, external or
    framework parents, registries, strategies, backends, providers, components, and plugin APIs
    are excluded. Decorated classes, metaclasses, multiple inheritance, exported bases, star
    imports, extra references, multiple children, and descendant chains also abstain. Public
    extension points should remain explicit even when the current repository has one subclass.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       # support.py
       class ServiceSupport:
           def normalize(self, value: str) -> str:
               return value.strip()

       # service.py
       from .support import ServiceSupport

       class Service(ServiceSupport):
           pass

    Good
    ~~~~
    .. code-block:: python

       class Service:
           def normalize(self, value: str) -> str:
               return value.strip()

       class StoragePlugin(Protocol):
           def store(self, value: bytes) -> None: ...

    References
    ----------
    Generalizes Pylint R0901 too-many-ancestors
    Cites "The Python Language Reference", custom classes
    https://docs.python.org/3.14/reference/datamodel.html#custom-classes
    Cites "The Python Standard Library", abc
    https://docs.python.org/3.14/library/abc.html
    Cites "PEP 544, Protocols"
    https://peps.python.org/pep-0544/
    Cites "The Python Language Reference", import system, import-related module attributes
    https://docs.python.org/3.14/reference/import.html#import-related-module-attributes
    Cites "Python Packaging User Guide", creating and discovering plugins
    https://packaging.python.org/guides/creating-and-discovering-plugins/
    Cites "Pydantic documentation", models
    https://docs.pydantic.dev/latest/concepts/models/
    """
    facts = subject.lazy(ClassRelation.FACTS)
    direct_subclasses = (
        subject.lazy(ClassRelation.DIRECT_SUBCLASSES)
        .group_by("class_id", maintain_order=True)
        .agg(pl.col("value").sort_by("ordinal").alias("direct_subclasses"))
    )
    decorator_counts = (
        subject.lazy(ClassRelation.CLASS_DECORATORS)
        .group_by("class_id", maintain_order=True)
        .agg(pl.len().cast(pl.UInt64).alias("decorator_count"))
    )
    keyword_counts = (
        subject.lazy(ClassRelation.CLASS_KEYWORDS)
        .group_by("class_id", maintain_order=True)
        .agg(pl.len().cast(pl.UInt64).alias("keyword_count"))
    )
    invalid_bases = (
        subject.lazy(ClassRelation.DIRECT_BASES)
        .filter(pl.col("value") != "object")
        .group_by("class_id", maintain_order=True)
        .agg(pl.len().cast(pl.UInt64).alias("invalid_base_count"))
    )
    evidence = (
        subject.lazy(ClassRelation.EVIDENCE)
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("signal").sort_by("ordinal").alias("evidence"))
    )
    selected = (
        subject.lazy(ClassRelation.CLASSES)
        .join(direct_subclasses, on="class_id", how="left")
        .join(decorator_counts, on="class_id", how="left")
        .join(keyword_counts, on="class_id", how="left")
        .join(invalid_bases, on="class_id", how="left")
        .with_columns(
            pl.col("direct_subclasses").fill_null(pl.lit([], dtype=pl.List(pl.String))),
            pl.col("decorator_count").fill_null(0),
            pl.col("keyword_count").fill_null(0),
            pl.col("invalid_base_count").fill_null(0),
        )
        .filter(
            (pl.col("scope") == "module")
            & (pl.col("direct_subclasses").list.len() == 1)
            & (pl.col("descendant_count") == 1)
            & (pl.col("decorator_count") == 0)
            & (pl.col("keyword_count") == 0)
            & (pl.col("invalid_base_count") == 0)
            & ~pl.col("is_instantiated")
            & ~pl.col("is_exported")
            & pl.col("only_cross_module_reference_is_subclass")
        )
        .join(evidence, on="fact_id", how="left")
        .with_columns(pl.col("evidence").fill_null(pl.lit([], dtype=pl.List(pl.String))))
    )
    counts = selected.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("value")
    )
    frame = facts.join(counts, on="fact_id", how="left").with_columns(pl.col("value").fill_null(0))
    return RuleQuery.integer(
        frame,
        pl.col("value"),
        findings=FindingQuery.build(
            selected,
            pl.concat_str(
                pl.lit("`"),
                pl.col("name"),
                pl.lit("` exists only as the base of `"),
                pl.col("direct_subclasses").list.first(),
                pl.lit("`"),
            ),
            (("artificial single subclass base count", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
    )
