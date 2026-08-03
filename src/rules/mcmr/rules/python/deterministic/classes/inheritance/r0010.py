import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import ClassFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import ClassRelation, Table


@rule("PY-CLAS0006")
def pass_through_inheritance_layer_count(
    subject: Table[ClassFact],
    *,
    contract_suffixes: tuple[str, ...] = (
        "Backend",
        "Error",
        "Exception",
        "Mixin",
        "Plugin",
        "Port",
        "Protocol",
        "Provider",
        "Registry",
        "Strategy",
    ),
) -> CountQuery:
    """Count project-owned inheritance layers that add only a name or forwarding frame.

    Definition
    ----------
    Resolve top-level project classes and their direct bases across relative and absolute imports.
    Report an undecorated single-inheritance subclass when its body is only `pass` or an ellipsis,
    or when every body member is an ordinary method that returns the same-named zero-argument
    `super()` method with every positional, variadic, keyword-only, and keyword variadic argument
    unchanged. The existing closed-world single-subclass-base rule owns a pair when the base itself
    can be removed, so this rule abstains from that exact overlap.

    Evidence
    --------
    Each finding identifies the fully qualified project base, layer kind, complete child range, and
    every transparently forwarded method. The result counts shallow child layers rather than base
    classes. The value is the number of shallow child layers rather than the number of bases
    beneath them.

    Exceptions
    ----------
    Decorated classes, class keywords, multiple or external bases, changed arguments, transformed
    returns, asynchronous adapters, descriptors, class methods, and static methods are excluded. A
    name ending in one of the `contract_suffixes` is an intentional type contract, which by default
    covers a protocol, a port, a mixin, a plugin, a strategy, a backend, a provider, a registry,
    and an error. A body holding only a docstring is a class that stated why it exists, so it is
    not a layer nobody meant to add. Keep an otherwise empty class when runtime registration or
    external consumers rely on its identity and disable this preference for that path.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       class JsonSerializer(Serializer):
           pass

       class NamedParser(Parser):
           def parse(self, text: str) -> Node:
               return super().parse(text)

    Good
    ~~~~
    .. code-block:: python

       class JsonSerializer(Serializer):
           def encode(self, value: JsonValue) -> bytes:
               return json.dumps(value).encode()

       class StoragePlugin(Protocol):
           def store(self, payload: bytes) -> None: ...

    References
    ----------
    Generalizes Pylint R0901 too-many-ancestors
    Generalizes Pylint W0246 useless-parent-delegation
    Cites "The Python Language Reference", custom classes
    https://docs.python.org/3/reference/datamodel.html#custom-classes
    Cites "PEP 544, Protocols"
    https://peps.python.org/pep-0544/
    Cites "A Philosophy of Software Design", chapters 4 and 7
    """
    facts = subject.lazy(ClassRelation.FACTS)
    direct_bases = (
        subject.lazy(ClassRelation.DIRECT_BASES)
        .group_by("class_id", maintain_order=True)
        .agg(pl.col("value").sort_by("ordinal").alias("direct_bases"))
    )
    decorator_counts = (
        subject.lazy(ClassRelation.CLASS_DECORATORS)
        .group_by("class_id", maintain_order=True)
        .agg(pl.len().cast(pl.UInt64).alias("decorator_count"))
    )
    evidence = (
        subject.lazy(ClassRelation.EVIDENCE)
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("signal").sort_by("ordinal").alias("evidence"))
    )
    contract_name = (
        pl.any_horizontal([pl.col("name").str.ends_with(suffix) for suffix in contract_suffixes])
        if contract_suffixes
        else pl.lit(False)
    )
    selected = (
        subject.lazy(ClassRelation.CLASSES)
        .join(direct_bases, on="class_id", how="left")
        .join(decorator_counts, on="class_id", how="left")
        .with_columns(
            pl.col("direct_bases").fill_null(pl.lit([], dtype=pl.List(pl.String))),
            pl.col("decorator_count").fill_null(0),
        )
        .filter(
            (pl.col("scope") == "module")
            & (pl.col("direct_bases").list.len() == 1)
            & (pl.col("decorator_count") == 0)
            & pl.col("is_pass_through_layer")
            & ~pl.col("base_is_removable_overlap")
            & ~contract_name
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
                pl.lit("` passes through its only base `"),
                pl.col("direct_bases").list.first(),
                pl.lit("`"),
            ),
            (("pass through inheritance layer count", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
    )
