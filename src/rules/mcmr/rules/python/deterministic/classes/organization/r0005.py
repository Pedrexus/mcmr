import polars as pl
from pydantic import NonNegativeInt

from ...... import rule
from ......domain.contracts import Unit
from ......facts import ClassFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import ClassRelation, Table


@rule("PY-CLAS0002")
def coupled_nested_type_candidate(
    subject: Table[ClassFact],
    *,
    suffixes: tuple[str, ...] = ("Content", "Kind"),
    minimum_types: NonNegativeInt = 2,
    minimum_coimports: NonNegativeInt = 2,
    maximum_type_lines: NonNegativeInt = 30,
    minimum_prefix_length: NonNegativeInt = 3,
) -> CountQuery:
    """Find short tightly named classes that may form one nested namespace.

    Definition
    ----------
    Find top-level classes whose names share a prefix and end in configured role suffixes. Require
    at least `minimum_types`, require every class to span no more than `maximum_type_lines`, and
    require at least `minimum_coimports` other modules to import two or more of the classes from
    the same defining module. The default recognizes pairs such as `MessageContent` and
    `MessageKind`. The value is the number of qualifying groups.

    Evidence
    --------
    Findings identify the definitions and every qualifying co-import site. The proposed namespace
    is the shared prefix, producing access such as `Message.Content` and `Message.Kind`. The value
    is the number of qualifying groups rather than the number of classes in them.

    Exceptions
    ----------
    Nested classes do not capture an outer instance and change `__qualname__`, import paths,
    pickling identity, framework discovery, and public APIs. Keep top-level classes when either
    type is independently useful, subclassed externally, registered by qualified name, or easier to
    test separately. A small module namespace can be clearer than a namespace-only class. This is
    an opt-in candidate rule and has no automatic fix. `minimum_prefix_length` keeps a one or two
    character shared prefix from grouping unrelated classes, since a namespace named after two
    letters explains nothing.

    Examples
    --------
    Two twelve-line classes named `EventContent` and `EventKind` that are imported together by
    three modules are reported as an `Event` namespace candidate. A large `EventContent`, a
    `Kind` used alone, or a pair imported together only once is not reported.

    References
    ----------
    Cites "The Python Tutorial", class namespaces and scopes
    https://docs.python.org/3/tutorial/classes.html
    Cites "Google Python Style Guide", nested classes and functions
    https://google.github.io/styleguide/pyguide.html#262-pros
    """
    facts = subject.lazy(ClassRelation.FACTS)
    role_suffixes = (
        subject.lazy(ClassRelation.COUPLED_GROUP_SUFFIXES)
        .group_by("group_id", maintain_order=True)
        .agg(pl.col("suffix").sort_by("ordinal").alias("role_suffixes"))
    )
    evidence = (
        subject.lazy(ClassRelation.EVIDENCE)
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("signal").sort_by("ordinal").alias("evidence"))
    )
    selected = (
        subject.lazy(ClassRelation.COUPLED_GROUPS)
        .join(role_suffixes, on="group_id", how="left")
        .with_columns(pl.col("role_suffixes").fill_null(pl.lit([], dtype=pl.List(pl.String))))
        .filter(
            (pl.col("prefix").str.len_chars() >= minimum_prefix_length)
            & (pl.col("role_suffixes").list.set_difference(list(suffixes)).list.len() == 0)
            & (pl.col("type_count") >= minimum_types)
            & (pl.col("maximum_type_lines") <= maximum_type_lines)
            & (pl.col("coimporting_module_count") >= minimum_coimports)
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
                pl.col("prefix"),
                pl.lit("` groups "),
                pl.col("type_count"),
                pl.lit(" short types ending in `"),
                pl.col("role_suffixes").list.join("`, `"),
                pl.lit("` and they are co-imported by "),
                pl.col("coimporting_module_count"),
                pl.lit(" modules"),
            ),
            (("coupled nested type candidate", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
    )
