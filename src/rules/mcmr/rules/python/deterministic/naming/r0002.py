import polars as pl

from ..... import rule
from .....domain.contracts import (
    FixSafety,
    Unit,
)
from .....facts import SymbolFact
from .....query import FindingQuery, OccurrenceQuery, RuleQuery
from .....table import Table
from ..symbol_relations import SymbolRelations, predicate_fix


@rule("PY-NAMI0001", fix_safety=FixSafety.REVIEW)
def boolean_predicate_name(
    subject: Table[SymbolFact],
    *,
    prefixes: tuple[str, ...] = ("is_", "has_", "can_", "should_", "supports_"),
) -> OccurrenceQuery:
    """Require Boolean symbols to read as predicates.

    Definition
    ----------
    Require attributes, properties, functions, and methods proven to return Boolean values to begin
    with a configured question prefix after removing any visibility prefix. The default prefixes
    are `is_`, `has_`, `can_`, `should_`, and `supports_`.

    Evidence
    --------
    Each finding names the symbol, the exact place it is declared, and how many references a
    rename would have to move with it, which is what says whether the repair is safe. The rename
    itself arrives from the fix this rule already declares rather than from a second statement of
    the same edit. A symbol whose references are incomplete is reported and left unrepaired.

    Exceptions
    ----------
    Exclude local variables, Python special methods, required overrides, and names imposed by an
    external framework or protocol.

    Examples
    --------
    `ready: bool` fails while `is_ready: bool` passes. A required `__contains__` method is excluded
    even though it returns `bool`.

    References
    ----------
    Adapts Pylint C0103 invalid-name
    Cites "PEP 8, Style Guide for Python Code", naming conventions
    Cites "The Python Standard Library", predicate naming conventions
    Cites "Clean Code", meaningful names
    """
    relations = SymbolRelations(subject)
    bare_name = pl.col("name").str.strip_chars_start("_")
    marked = (
        pl.any_horizontal([bare_name.str.starts_with(prefix) for prefix in prefixes])
        if prefixes
        else pl.lit(False)
    )
    selected = relations.symbols().filter(pl.col("returns_boolean") & ~marked)
    counts = selected.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("unmarked_count")
    )
    frame = (
        relations.facts()
        .join(counts, on="fact_id", how="left")
        .with_columns((pl.col("unmarked_count").fill_null(0) > 0).alias("value"))
    )
    findings = FindingQuery.build(
        selected,
        pl.concat_str(
            pl.lit("`"),
            pl.col("name"),
            pl.lit(
                "` answers with a Boolean and its name does not say so, since it opens with "
                "none of "
            ),
            pl.lit(", ".join(f"`{prefix}`" for prefix in prefixes)),
        ),
        (("references a rename would move", pl.col("reference_count"), Unit.COUNT),),
        finding_order=pl.col("ordinal"),
        evidence=pl.col("evidence"),
    )
    fix = predicate_fix(relations, selected, prefixes[0]) if prefixes else None
    return RuleQuery.boolean(frame, pl.col("value"), findings=findings, fix=fix)
