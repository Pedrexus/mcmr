import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import ClassFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import ClassRelation, Table


@rule("PY-CLAS0004")
def staticmethod_calling_classmethod_count(
    subject: Table[ClassFact],
) -> CountQuery:
    """Count static methods that hard-code their owner to call a sibling class method.

    Definition
    ----------
    Inspect methods declared directly in each class. Report a method only when its sole decorator
    is `staticmethod`, the same class directly declares at least one `classmethod`, and the static
    body calls that sibling through the literal owning class name. Calls inside nested functions
    and methods whose local bindings shadow the class name are excluded. The result is the number
    of affected static methods.

    Evidence
    --------
    Each finding identifies the static method and every sibling class method it calls. The literal
    owner reference is the proof that the method already depends on class-level behavior. The value
    is the number of static methods calling a sibling class method through the owner name.

    Exceptions
    ----------
    Calls to another class, an instance method, a static sibling, or an inherited method are not
    inferred. Custom-decorated static methods are excluded because changing descriptor order may
    alter framework behavior. A deliberate non-polymorphic call to one concrete class may remain
    static when the project documents that choice and disables this preference.

    Examples
    --------
    Bad
    ~~~
    `Parser.decide` is a static method whose body calls `Parser.from_text(...)`, where `from_text`
    is a class method. Subclasses cannot redirect that hard-coded call.

    Good
    ~~~~
    Make `decide` a class method, accept `cls`, and call `cls.from_text(...)`. A static method that
    only calls another static method remains unchanged.

    References
    ----------
    Cites "The Python Standard Library", `classmethod`
    https://docs.python.org/3/library/functions.html#classmethod
    Cites "The Python Standard Library", `staticmethod`
    https://docs.python.org/3/library/functions.html#staticmethod
    Cites "The Python Language Reference", descriptor invocation
    https://docs.python.org/3/reference/datamodel.html#invoking-descriptors
    """
    facts = subject.lazy(ClassRelation.FACTS)
    classes = subject.lazy(ClassRelation.CLASSES).select(
        "class_id",
        "fact_id",
        pl.col("name").alias("class_name"),
        pl.col("ordinal").alias("class_ordinal"),
    )
    methods = subject.lazy(ClassRelation.METHODS).join(classes, on="class_id", how="inner")
    decorators = (
        subject.lazy(ClassRelation.METHOD_DECORATORS)
        .group_by("method_id", maintain_order=True)
        .agg(pl.col("value").sort_by("ordinal").alias("decorators"))
    )
    owner_calls = (
        subject.lazy(ClassRelation.OWNER_QUALIFIED_CALLS)
        .group_by("method_id", maintain_order=True)
        .agg(pl.col("value").sort_by("ordinal").alias("owner_qualified_calls"))
    )
    class_method_calls = (
        methods.filter(pl.col("kind") == "class_method")
        .with_columns(pl.concat_str("class_name", pl.lit("."), "name").alias("expected_call"))
        .group_by("class_id", maintain_order=True)
        .agg(pl.col("expected_call").alias("class_method_calls"))
    )
    evidence = (
        subject.lazy(ClassRelation.EVIDENCE)
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("signal").sort_by("ordinal").alias("evidence"))
    )
    selected = (
        methods.join(decorators, on="method_id", how="left")
        .join(owner_calls, on="method_id", how="left")
        .join(class_method_calls, on="class_id", how="left")
        .with_columns(
            pl.col("decorators").fill_null(pl.lit([], dtype=pl.List(pl.String))),
            pl.col("owner_qualified_calls").fill_null(pl.lit([], dtype=pl.List(pl.String))),
            pl.col("class_method_calls").fill_null(pl.lit([], dtype=pl.List(pl.String))),
        )
        .filter(
            (pl.col("kind") == "static_method")
            & (pl.col("decorators") == pl.lit(["staticmethod"]))
            & (
                pl.col("owner_qualified_calls")
                .list.set_intersection(pl.col("class_method_calls"))
                .list.len()
                > 0
            )
        )
        .join(evidence, on="fact_id", how="left")
        .with_columns(pl.col("evidence").fill_null(pl.lit([], dtype=pl.List(pl.String))))
    )
    counts = selected.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("value")
    )
    frame = facts.join(counts, on="fact_id", how="left").with_columns(pl.col("value").fill_null(0))
    finding_order = pl.col("class_ordinal").cast(pl.UInt64) * pl.lit(
        1 << 32, dtype=pl.UInt64
    ) + pl.col("ordinal")
    return RuleQuery.integer(
        frame,
        pl.col("value"),
        findings=FindingQuery.build(
            selected,
            pl.concat_str(
                pl.lit("static method `"),
                pl.col("class_name"),
                pl.lit("."),
                pl.col("name"),
                pl.lit("` hard-codes its owner to call a sibling class method"),
            ),
            (("staticmethod calling classmethod count", pl.lit(1), Unit.COUNT),),
            finding_order=finding_order,
            evidence=pl.col("evidence"),
        ),
    )
