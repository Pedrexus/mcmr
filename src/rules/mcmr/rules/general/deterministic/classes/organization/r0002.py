from collections.abc import Sequence

import polars as pl

from ...... import rule
from ......domain.contracts import FixSafety, Unit
from ......facts import ClassFact, MemberKind, Visibility
from ......query import CountQuery, FindingQuery, FixQuery, RuleQuery
from ......table import ClassRelation, Table


def _configured_rank(column: str, values: Sequence[str]) -> pl.Expr:
    """Build one stable configured rank with unlisted values placed last."""
    rank = pl.lit(len(values), dtype=pl.UInt64)
    for index, value in reversed(list(enumerate(values))):
        rank = (
            pl.when(pl.col(column) == value).then(pl.lit(index, dtype=pl.UInt64)).otherwise(rank)
        )
    return rank


def _misordered_regions(
    subject: Table[ClassFact],
    *,
    lifecycle: Sequence[str],
    visibility_order: Sequence[str],
    kind_order: Sequence[str],
    alphabetical: bool,
) -> tuple[pl.LazyFrame, pl.LazyFrame]:
    """Return fact rows and the first mismatched region for each unordered class."""
    facts = subject.lazy(ClassRelation.FACTS)
    classes = subject.lazy(ClassRelation.CLASSES).select(
        "class_id",
        "fact_id",
        pl.col("name").alias("class_name"),
        pl.col("ordinal").alias("class_ordinal"),
        pl.col("path").alias("class_path"),
        pl.col("start_line").alias("class_start_line"),
        pl.col("start_column").alias("class_start_column"),
        pl.col("end_line").alias("class_end_line"),
        pl.col("end_column").alias("class_end_column"),
    )
    methods = subject.lazy(ClassRelation.METHODS).join(classes, on="class_id", how="inner")
    lifecycle_rank = _configured_rank("name", lifecycle)
    visibility_rank = _configured_rank("visibility", visibility_order)
    kind_rank = _configured_rank("kind", kind_order)
    category = (
        pl.when(lifecycle_rank < len(lifecycle))
        .then(pl.lit(0, dtype=pl.UInt64))
        .when(pl.col("is_protocol_name"))
        .then(pl.lit(1, dtype=pl.UInt64))
        .otherwise(pl.lit(2, dtype=pl.UInt64))
    )
    first_rank = (
        pl.when(category == 0)
        .then(lifecycle_rank)
        .when(category == 1)
        .then(pl.lit(0, dtype=pl.UInt64))
        .otherwise(visibility_rank)
    )
    second_rank = pl.when(category < 2).then(pl.lit(0, dtype=pl.UInt64)).otherwise(kind_rank)
    sort_name = pl.col("name").str.to_lowercase() if alphabetical else pl.lit("")
    regions = (
        methods.with_columns(
            category.alias("sort_category"),
            first_rank.alias("sort_first"),
            second_rank.alias("sort_second"),
            sort_name.alias("sort_name"),
        )
        .group_by("class_id", "fact_id", "class_ordinal", "region", maintain_order=True)
        .agg(
            pl.col("class_name").first(),
            pl.col("class_path").first(),
            pl.col("class_start_line").first(),
            pl.col("class_start_column").first(),
            pl.col("class_end_line").first(),
            pl.col("class_end_column").first(),
            pl.col("method_id").sort_by("ordinal").alias("declared"),
            pl.col("method_id")
            .sort_by("sort_category", "sort_first", "sort_second", "sort_name", "ordinal")
            .alias("expected"),
            pl.col("name").sort_by("ordinal").alias("declared_names"),
            pl.col("name")
            .sort_by("sort_category", "sort_first", "sort_second", "sort_name", "ordinal")
            .alias("expected_names"),
        )
        .filter(pl.col("declared") != pl.col("expected"))
        .with_columns(pl.col("declared").list.len().alias("declared_count"))
        .explode("declared", "expected", "declared_names", "expected_names", empty_as_null=True)
        .filter(pl.col("declared") != pl.col("expected"))
        .group_by("class_id", "fact_id", "class_ordinal", "region", maintain_order=True)
        .agg(
            pl.col("class_name").first(),
            pl.col("class_path").first(),
            pl.col("class_start_line").first(),
            pl.col("class_start_column").first(),
            pl.col("class_end_line").first(),
            pl.col("class_end_column").first(),
            pl.col("declared_count").first(),
            pl.len().cast(pl.UInt64).alias("moved_count"),
            pl.col("declared").first().alias("declared_id"),
            pl.col("expected").first().alias("expected_id"),
            pl.col("declared_names").first().alias("declared_name"),
            pl.col("expected_names").first().alias("expected_name"),
        )
        .sort("fact_id", "class_ordinal", "region")
        .unique("class_id", keep="first", maintain_order=True)
        .with_columns(
            pl.col("class_path").alias("path"),
            pl.col("class_start_line").alias("start_line"),
            pl.col("class_start_column").alias("start_column"),
            pl.col("class_end_line").alias("end_line"),
            pl.col("class_end_column").alias("end_column"),
        )
    )
    return facts, regions


@rule("ALL-CLAS0001", fix_safety=FixSafety.REVIEW)
def class_method_order(
    subject: Table[ClassFact],
    *,
    lifecycle: Sequence[str] = (
        "__init_subclass__",
        "__new__",
        "__init__",
        "__post_init__",
        "model_post_init",
    ),
    visibility_order: Sequence[str] = (
        Visibility.PUBLIC,
        Visibility.PROTECTED,
        Visibility.INTERNAL,
        Visibility.PRIVATE,
    ),
    kind_order: Sequence[str] = (
        MemberKind.CONSTRUCTOR,
        MemberKind.PROPERTY,
        MemberKind.STATIC_METHOD,
        MemberKind.CLASS_METHOD,
        MemberKind.METHOD,
    ),
    alphabetical: bool = True,
) -> CountQuery:
    """Count classes whose methods do not follow one explicit source order.

    Definition
    ----------
    Inspect methods declared directly in each class. Put the configured lifecycle names first in
    their declared sequence, then the language protocol members a provider marks as such. Order
    every remaining method by visibility, then by member kind, then case-insensitively by name when
    `alphabetical` is true. A `# region` boundary or its language equivalent starts a new
    independently ordered section. Accessors that share one name, such as a property setter beside
    its getter, stay stable. The value is the number of classes whose current order differs.

    Every language that declares members inside a type takes part. A provider maps its own spelling
    onto the shared visibility and member kinds, so a Java `private static` helper, a Rust
    associated function, a TypeScript `#field` accessor, and a Python `classmethod` all sort under
    one declared policy rather than a Python-shaped category list.

    Evidence
    --------
    Each finding names the class, its range in the file, and the first member that sits
    somewhere other than where the declared order puts it, beside how many members the class
    declares and how many of them are out of place. The review repair moves the first displaced
    method to its expected position and preserves its source exactly. Lifecycle names, visibility
    order, and kind order are all configurable, and a member whose visibility or kind is left out
    of the configured order sorts after every configured one. `visibility_order` and `kind_order`
    are the two sorts applied after
    the lifecycle names, so a project that puts protected members first or class methods before
    properties states that order rather than accepting this one. The value is the number of classes
    whose declared order differs from the expected one.

    Exceptions
    ----------
    Decorators execute while a class body is built, and one declaration can refer to an earlier
    descriptor. The fix therefore requires review instead of applying as a safe edit. Keep
    required adjacency or execution order by splitting the class or introducing named regions.
    Disable WPS338 and CCE001 when this rule owns the same class. Alphabetical order is a project
    preference rather than a language requirement.

    Examples
    --------
    A public property followed by `__init__` is reported because lifecycle methods come first.
    Public methods `save` and `open` are reported when alphabetical ordering is enabled because
    `open` precedes `save`. A property getter immediately followed by its setter remains stable.

    References
    ----------
    Generalizes wemake-python-styleguide WPS338
    https://wemake-python-styleguide.readthedocs.io/en/latest/pages/usage/violations/consistency.html
    Generalizes flake8-class-attributes-order CCE001
    https://github.com/best-doctor/flake8-class-attributes-order
    Cites "Google Java Style Guide", ordering of class contents
    https://google.github.io/styleguide/javaguide.html#s3.4.2-ordering-class-contents
    """
    facts, regions = _misordered_regions(
        subject,
        lifecycle=lifecycle,
        visibility_order=visibility_order,
        kind_order=kind_order,
        alphabetical=alphabetical,
    )
    counts = regions.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("value")
    )
    frame = facts.join(counts, on="fact_id", how="left").with_columns(pl.col("value").fill_null(0))
    methods = subject.lazy(ClassRelation.METHODS)
    fixable = (
        regions.join(
            methods.select(
                pl.col("method_id").alias("expected_id"),
                pl.col("path").alias("target_path"),
                pl.col("start_line").alias("target_start_line"),
                pl.col("start_column").alias("target_start_column"),
                pl.col("end_line").alias("target_end_line"),
                pl.col("end_column").alias("target_end_column"),
                pl.col("kind").alias("target_kind"),
                pl.col("source").alias("target_text"),
            ),
            on="expected_id",
            how="inner",
        )
        .join(
            methods.select(
                pl.col("method_id").alias("declared_id"),
                pl.col("path").alias("anchor_path"),
                pl.col("start_line").alias("anchor_start_line"),
                pl.col("start_column").alias("anchor_start_column"),
                pl.col("end_line").alias("anchor_end_line"),
                pl.col("end_column").alias("anchor_end_column"),
                pl.col("kind").alias("anchor_kind"),
                pl.col("source").alias("anchor_text"),
            ),
            on="declared_id",
            how="inner",
        )
        .with_row_index("rewrite_order")
    )
    rewrites = fixable.select(
        "fact_id",
        pl.col("rewrite_order").cast(pl.UInt64),
        pl.lit("move").alias("kind"),
        pl.lit("").alias("source"),
        pl.lit("before").alias("placement"),
        pl.lit("").alias("name"),
        pl.lit("").alias("symbol_id"),
        pl.lit("").alias("symbol_name"),
        pl.lit(False).alias("references_complete"),
    )
    nodes = pl.concat(
        [
            fixable.select(
                "fact_id",
                pl.col("rewrite_order").cast(pl.UInt64),
                pl.lit(role).alias("role"),
                pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
                pl.col(f"{identity}_id").alias("id"),
                pl.col(f"{role}_path").alias("path"),
                pl.col(f"{role}_start_line").cast(pl.UInt64).alias("start_line"),
                pl.col(f"{role}_start_column").cast(pl.UInt64).alias("start_column"),
                pl.col(f"{role}_end_line").cast(pl.UInt64).alias("end_line"),
                pl.col(f"{role}_end_column").cast(pl.UInt64).alias("end_column"),
                pl.col(f"{role}_kind").alias("kind"),
                pl.col(f"{role}_text").alias("text"),
            )
            for role, identity in [("target", "expected"), ("anchor", "declared")]
        ]
    )
    declared_members = pl.concat_str(
        pl.col("declared_count"),
        pl.when(pl.col("declared_count") == 1)
        .then(pl.lit(" member"))
        .otherwise(pl.lit(" members")),
    )
    return RuleQuery.integer(
        frame,
        pl.col("value"),
        findings=FindingQuery.build(
            regions,
            pl.concat_str(
                pl.lit("`"),
                pl.col("class_name"),
                pl.lit("` declares "),
                pl.col("moved_count"),
                pl.lit(" of its "),
                declared_members,
                pl.lit(" out of order, and `"),
                pl.col("expected_name"),
                pl.lit("` belongs where `"),
                pl.col("declared_name"),
                pl.lit("` sits"),
            ),
            (
                ("declared members", pl.col("declared_count"), Unit.COUNT),
                ("members out of place", pl.col("moved_count"), Unit.COUNT),
            ),
            finding_order=pl.col("class_ordinal"),
        ),
        fix=FixQuery.build(
            "Move the first displaced method to its configured position.",
            rewrites=rewrites,
            nodes=nodes,
        ),
    )
