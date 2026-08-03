import polars as pl

from ...... import rule
from ......facts import LiteralGroupFact
from ......query import FindingQuery, OccurrenceQuery, RuleQuery
from ......table import Table


@rule("PY-ENUM0002")
def parallel_enum_metadata(subject: Table[LiteralGroupFact]) -> OccurrenceQuery:
    """Detect static string dictionaries that mirror one enum.

    Definition
    ----------
    A parallel metadata dictionary has at least two entries, uses members of one locally
    defined enum as every key, and uses string literals as every value. The enum can own
    these descriptions directly and generate the dictionary when an API needs one.

    Evidence
    --------
    Every finding identifies one parallel dictionary expression and its enum class.

    Exceptions
    ----------
    Dynamic handler registries, non-string values, partial runtime overrides, and mappings
    across several enum types remain separate data structures.

    Examples
    --------
    `{Intent.TODO: "Future work", Intent.WHY: "Rationale"}` mirrors static enum
    descriptions. `{Intent.TODO: handle_todo}` remains a behavior registry.

    References
    ----------
    Cites "Refactoring", Parallel Inheritance Hierarchies
    """
    relations = subject
    selected = relations.records("enum_metadata_maps").filter(
        pl.col("all_keys_resolve_to_enum")
        & (pl.col("keys.length") >= 2)
        & (pl.col("keys.length") == pl.col("values.length"))
    )
    counts = selected.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("selected_count")
    )
    frame = (
        relations.facts()
        .join(counts, on="fact_id", how="left")
        .with_columns(pl.col("selected_count").fill_null(0))
    )
    value = pl.col("selected_count") > 0
    return RuleQuery.boolean(
        frame,
        value,
        findings=FindingQuery.precise_boolean(
            frame,
            value,
            "parallel enum metadata",
            evidence=pl.col("evidence"),
        ),
    )
