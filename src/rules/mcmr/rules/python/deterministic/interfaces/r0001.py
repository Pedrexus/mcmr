import polars as pl

from ..... import rule
from .....facts import RuntimeTypeCheckFact
from .....query import FindingQuery, OccurrenceQuery, RuleQuery
from .....table import Table


@rule("PY-INTE0001")
def concrete_isinstance_capability(subject: Table[RuntimeTypeCheckFact]) -> OccurrenceQuery:
    """Detect concrete runtime checks that stand in for a capability.

    Definition
    ----------
    Find `isinstance` checks against concrete numeric and container built-ins. Infer the
    narrowest standard runtime capability from operations in the immediately guarded block.
    Prefer EAFP when the code can simply perform one operation and handle its documented
    exception. The rule reports candidates and never rewrites them automatically because an
    ABC deliberately accepts more implementations than a concrete built-in.

    Evidence
    --------
    Each finding names the concrete types, inferred ABC or protocol, and source location.

    Exceptions
    ----------
    Exact built-in checks remain valid at JSON, TOML, database, wire-format, C-extension,
    dispatch, and other representation boundaries. Nothing in the source says a value arrived
    from one, because what `tomllib` hands back is an ordinary `dict` by the time a check reads
    it, so a project names the modules that sit on such a boundary in the `exclude` list its rule
    configuration accepts rather than leaving this rule to guess. `str` and `bool` stay concrete
    because their domain meaning is commonly more specific than their inherited capabilities.

    Examples
    --------
    `isinstance(index, int)` guarding arithmetic returns `true` and prefers `numbers.Integral`. An
    indexed read guarded by `isinstance(items, (list, tuple))` returns `true` and prefers
    `collections.abc.Sequence`, including where the guarded block only iterates or measures.
    `isinstance(name, str)` returns `false`, because `str` stays concrete, and so does a check with
    no guarded operation to infer a capability from.

    References
    ----------
    Cites "Fluent Python", chapter 13, Interfaces, Protocols, and ABCs
    Cites "The Python Standard Library", `collections.abc`
    Cites "The Python Standard Library", `numbers` documentation and PEP 3141
    """
    relations = subject
    selected = relations.records("checks").filter(
        pl.col("concrete_type").is_in(["list", "tuple", "dict", "set", "int", "float", "complex"])
        & (pl.col("guarded_operations.length") > 0)
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
            "concrete isinstance capability",
            evidence=pl.col("evidence"),
        ),
    )
