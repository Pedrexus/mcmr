import polars as pl

from ..... import Numeric, rule
from .....domain.contracts import Unit
from .....facts import ModuleSurfaceFact
from .....query import FindingQuery, PercentageQuery, RuleQuery
from .....table import Table

# What each hatch is called in a sentence, since a rule reading a kind has to say it in words a
# reader recognizes from their own source rather than as the field name the provider used.
_NAMED = {
    "assertion": "type assertion",
    "non_null": "non-null assertion",
    "any": "`any`",
    "ignore_comment": "suppression comment",
}


@rule("TS-TYPE0002", policy=Numeric(maximum=2))
def escape_hatch_density(subject: Table[ModuleSurfaceFact]) -> PercentageQuery:
    """Measure how much of a module steps around what its type system proved.

    Definition
    ----------
    Return the share of lines carrying a type assertion, a non-null assertion, an `any`, or a
    suppression comment. Each one is a promise to the compiler with nothing behind it, and the
    compiler stops checking exactly where the promise was made. One is a considered decision. A
    module where a tenth of the lines make one has stopped being typed, and no per-occurrence rule
    says so, because each occurrence looked reasonable on its own.

    Evidence
    --------
    Each finding names one hatch, its kind, and the line it sits on, beside the module's own length
    and the share every hatch together comes to. The repair is a choice, since validating at the
    boundary and excluding a declaration file are different answers to the same reading. The value
    is that share.

    Exceptions
    ----------
    A boundary that receives untyped data legitimately asserts once it has validated, and a schema
    validator is the usual way to make that assertion earn its keep. A declaration file describing
    an untyped library is assertions by nature. Both belong in a project's exclusions rather than
    in a raised ceiling.

    Examples
    --------
    A 200-line module with two assertions returns `1.0`. The same module with forty returns `20.0`
    and is no longer type checked in any meaningful sense.

    References
    ----------
    Generalizes typescript-eslint no-explicit-any
    Generalizes typescript-eslint no-non-null-assertion
    https://typescript-eslint.io/rules/no-explicit-any/
    Cites "TypeScript documentation", handbook, type assertions and their limits
    https://www.typescriptlang.org/docs/handbook/2/everyday-types.html#type-assertions
    Cites "Zod documentation", validating what the type system cannot prove at runtime
    https://zod.dev/
    """
    relations = subject
    facts = relations.facts().with_columns(
        pl.when(pl.col("physical_line_count") == 0)
        .then(0.0)
        .otherwise(pl.col("escape_hatches.length") / pl.col("physical_line_count") * 100.0)
        .alias("value")
    )
    selected = (
        relations.records("escape_hatches")
        .join(facts, on=["fact_order", "fact_id"], how="inner")
        .with_columns(
            pl.col("line").alias("start_line"),
            pl.lit(0, dtype=pl.UInt64).alias("start_column"),
            pl.col("line").alias("end_line"),
            pl.lit(0, dtype=pl.UInt64).alias("end_column"),
            pl.col("kind").replace_strict(_NAMED).alias("kind_name"),
        )
    )
    return RuleQuery.floating(
        facts,
        pl.col("value"),
        findings=FindingQuery.build(
            selected,
            pl.concat_str(
                pl.lit("`"),
                pl.col("path"),
                pl.lit("` states a "),
                pl.col("kind_name"),
                pl.lit(" here, one of "),
                pl.col("escape_hatches.length"),
                pl.when(pl.col("escape_hatches.length") == 1)
                .then(pl.lit(" place"))
                .otherwise(pl.lit(" places")),
                pl.lit(" it steps around its own types"),
            ),
            (
                ("hatches in the module", pl.col("escape_hatches.length"), Unit.COUNT),
                ("lines in the module", pl.col("physical_line_count"), Unit.COUNT),
                ("share of the module", pl.col("value"), Unit.PERCENTAGE),
            ),
            finding_order=pl.col("ordinal"),
            question=pl.concat_str(
                pl.lit("give the "),
                pl.col("kind_name"),
                pl.lit(" in `"),
                pl.col("path"),
                pl.lit("` something behind it"),
            ),
            options=(
                "validate the value and let the type follow from the check",
                "exclude a declaration file describing an untyped library",
            ),
            evidence=pl.col("evidence"),
        ),
    )
