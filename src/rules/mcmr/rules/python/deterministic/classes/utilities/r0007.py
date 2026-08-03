import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import ClassFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import ClassRelation, Table


@rule("PY-CLAS0003")
def utility_namespace_class_count(
    subject: Table[ClassFact],
) -> CountQuery:
    """Count stateless classes that only namespace module-shaped functions.

    Definition
    ----------
    Inspect every class in the selected Python sources. Require at least one directly declared
    synchronous or asynchronous function. Report the class when every function is static, class
    bound without reading class state, or an ordinary method that only calls sibling methods. The
    class must have no base other than `object`, no class keyword other than `metaclass=type`, and
    no instance-oriented field declaration or receiver-state read. Uppercase constants do not
    suppress the finding because module constants express the same ownership directly.

    Evidence
    --------
    Each finding identifies the class range, function count, and every qualifying function with
    its decorators. The result value is the number of stateless utility namespace classes.

    Exceptions
    ----------
    Nontrivial inheritance and metaclasses exempt framework contracts, enums, Protocols, and ABCs.
    Lowercase annotated fields, receiver assignments, `__slots__`, and attrs or dataclass field
    factories exempt data-bearing classes. Receiver state reads, properties, constructors,
    abstract methods, and custom decorators also exempt the whole class. Calling another method
    through `self` does not establish state. The rule reports structure only and does not
    automatically move functions because public access paths may be externally visible.

    Examples
    --------
    Bad
    ~~~
    `class TextTools` containing static helpers and `def render(self)` that only calls those
    helpers is reported because a module already provides the same namespace boundary.

    Good
    ~~~~
    `class Record` with an annotated `value` field is accepted. A `Protocol`, `Enum`, ABC,
    framework subclass, property-bearing class, or class whose ordinary method reads `self.value`
    is also accepted even when it contains static helpers.

    References
    ----------
    Adapts Pylint R0903 too-few-public-methods
    Cites "The Python Tutorial", modules as namespaces
    https://docs.python.org/3/tutorial/modules.html
    Cites "The Python Language Reference", class creation and metaclasses
    https://docs.python.org/3/reference/datamodel.html#customizing-class-creation
    Cites "The Python Standard Library", functions, `staticmethod`
    https://docs.python.org/3/library/functions.html#staticmethod
    Cites "The Python Standard Library", functions, `classmethod`
    https://docs.python.org/3/library/functions.html#classmethod
    Cites "PEP 544, Protocols"
    https://peps.python.org/pep-0544/
    """
    facts = subject.lazy(ClassRelation.FACTS)
    decorator_summary = (
        subject.lazy(ClassRelation.METHOD_DECORATORS)
        .group_by("method_id", maintain_order=True)
        .agg(
            pl.len().cast(pl.UInt64).alias("decorator_count"),
            (~pl.col("value").is_in(["staticmethod", "classmethod"]))
            .sum()
            .alias("invalid_decorator_count"),
        )
    )
    method_summary = (
        subject.lazy(ClassRelation.METHODS)
        .join(decorator_summary, on="method_id", how="left")
        .with_columns(
            pl.col("decorator_count").fill_null(0),
            pl.col("invalid_decorator_count").fill_null(0),
        )
        .with_columns(
            (
                (
                    ((pl.col("decorator_count") > 0) & (pl.col("invalid_decorator_count") == 0))
                    | ((pl.col("decorator_count") == 0) & (pl.col("kind") == "method"))
                )
                & ~pl.col("reads_receiver_state")
            ).alias("is_module_function")
        )
        .group_by("class_id", maintain_order=True)
        .agg(
            pl.col("is_module_function").all().alias("all_methods_are_module_functions"),
            pl.col("name").sort_by("ordinal").alias("method_names"),
        )
    )
    invalid_bases = (
        subject.lazy(ClassRelation.DIRECT_BASES)
        .filter(pl.col("value") != "object")
        .group_by("class_id", maintain_order=True)
        .agg(pl.len().cast(pl.UInt64).alias("invalid_base_count"))
    )
    invalid_keywords = (
        subject.lazy(ClassRelation.CLASS_KEYWORDS)
        .filter(pl.col("value") != "metaclass=type")
        .group_by("class_id", maintain_order=True)
        .agg(pl.len().cast(pl.UInt64).alias("invalid_keyword_count"))
    )
    evidence = (
        subject.lazy(ClassRelation.EVIDENCE)
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("signal").sort_by("ordinal").alias("evidence"))
    )
    selected = (
        subject.lazy(ClassRelation.CLASSES)
        .join(method_summary, on="class_id", how="inner")
        .join(invalid_bases, on="class_id", how="left")
        .join(invalid_keywords, on="class_id", how="left")
        .with_columns(
            pl.col("invalid_base_count").fill_null(0),
            pl.col("invalid_keyword_count").fill_null(0),
        )
        .filter(
            ~pl.col("is_test")
            & pl.col("all_methods_are_module_functions")
            & (pl.col("invalid_base_count") == 0)
            & (pl.col("invalid_keyword_count") == 0)
            & ~pl.col("has_instance_fields")
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
                pl.lit("` only namespaces `"),
                pl.col("method_names").list.join("`, `"),
                pl.lit("`"),
            ),
            (("utility namespace class count", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
    )
