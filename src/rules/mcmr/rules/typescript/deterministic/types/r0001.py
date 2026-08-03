import polars as pl

from ..... import Numeric, rule
from .....domain.contracts import Unit
from .....facts import ModuleSurfaceFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table import Table


@rule("TS-TYPE0001", policy=Numeric(maximum=0))
def non_erasable_construct(subject: Table[ModuleSurfaceFact]) -> CountQuery:
    """Count the constructs that stop TypeScript from being erased rather than compiled.

    Definition
    ----------
    Count the declarations whose meaning survives type stripping, which are an `enum`, a `const
    enum`, a runtime `namespace`, a constructor parameter property, and `import =`. Each generates
    JavaScript rather than disappearing with the types, which is why a runtime that strips types
    cannot run them and why TypeScript 5.8 added `erasableSyntaxOnly` to find them. Those semantics
    require emitted code.

    The cost is not only the build step. An `enum` produces an object with a reverse mapping that
    JSON never round-trips, a `namespace` produces a closure that tree shaking cannot open, and a
    parameter property hides a field declaration inside a signature.

    Evidence
    --------
    Each finding names the construct, its kind, and the line it is written on, counted against the
    module's own length. The repair is a choice, since rewriting the construct and deciding this
    project never strips types are both real answers. The value is the number found.

    Exceptions
    ----------
    A project that compiles through a bundler and never intends to strip types can keep them, and
    should say so by disabling this rule rather than by leaving it failing. A declaration file
    describing an external library states constructs it does not own.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: typescript

       enum Status { Active = 'ACTIVE' }
       class Engine { constructor(private limit: number) {} }

    Good
    ~~~~
    .. code-block:: typescript

       const Status = { Active: 'ACTIVE' } as const;
       type Status = (typeof Status)[keyof typeof Status];

    References
    ----------
    Cites "TypeScript documentation", 5.8 release notes, the `erasableSyntaxOnly` option
    https://www.typescriptlang.org/docs/handbook/release-notes/typescript-5-8.html
    Cites "Node.js documentation", type stripping
    https://nodejs.org/api/typescript.html
    Cites "TypeScript documentation", handbook, enums and their runtime output
    https://www.typescriptlang.org/docs/handbook/enums.html
    """
    relations = subject
    facts = relations.facts().with_columns(
        pl.col("erasable_violations.length").cast(pl.UInt64).alias("value")
    )
    selected = (
        relations.records("erasable_violations")
        .join(facts, on=["fact_order", "fact_id"], how="inner")
        .with_columns(
            pl.col("line").alias("start_line"),
            pl.lit(0, dtype=pl.UInt64).alias("start_column"),
            pl.col("line").alias("end_line"),
            pl.lit(0, dtype=pl.UInt64).alias("end_column"),
            pl.when(pl.col("name") == "")
            .then(pl.col("path"))
            .otherwise(pl.col("name"))
            .alias("display_name"),
        )
    )
    return RuleQuery.integer(
        facts,
        pl.col("value"),
        findings=FindingQuery.build(
            selected,
            pl.concat_str(
                pl.lit("`"),
                pl.col("display_name"),
                pl.lit("` is a "),
                pl.col("kind").str.replace_all("_", " "),
                pl.lit(", which generates JavaScript rather than disappearing with the types"),
            ),
            (
                ("constructs stripping cannot erase", pl.col("value"), Unit.COUNT),
                ("lines in the module", pl.col("physical_line_count"), Unit.COUNT),
            ),
            finding_order=pl.col("ordinal"),
            question=pl.concat_str(
                pl.lit("decide what `"),
                pl.col("display_name"),
                pl.lit("` is for"),
            ),
            options=(
                "state it as a value this language can erase around",
                "turn this rule off in a project that always compiles",
            ),
            evidence=pl.col("evidence"),
        ),
    )
