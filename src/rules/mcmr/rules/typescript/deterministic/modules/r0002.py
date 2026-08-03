import polars as pl

from ..... import Numeric, rule
from .....domain.contracts import Unit
from .....facts import ModuleSurfaceFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table import Table


@rule("TS-MODU0002", policy=Numeric(maximum=1))
def relative_import_depth(subject: Table[ModuleSurfaceFact]) -> CountQuery:
    """Measure how far a module climbs out of its own directory to find what it imports.

    Definition
    ----------
    Return the greatest number of parent directories any one import in this module traverses. A
    path that climbs three levels is telling you the two files belong to different parts of the
    system and somebody reached across anyway. It also breaks the moment either file moves, which
    is why the depth, rather than any single import, is the measurement worth having.

    Evidence
    --------
    The finding names the module and the deepest specifier it imports through, with the number of
    directories that specifier climbs. The repair is a choice, since an alias and a move fix the
    same climb differently. The value is that depth.

    Exceptions
    ----------
    A test that reaches into the tree it exercises climbs by design. A project with configured path
    aliases should see zero here, because an alias states the boundary the climb was hiding, which
    is the usual repair.

    Examples
    --------
    `import { User } from '../../../models/user'` returns `3` and wants an alias or a move.
    `import { User } from './models/user'` returns `0`.

    References
    ----------
    Cites "TypeScript documentation", handbook, module resolution and path mapping
    https://www.typescriptlang.org/docs/handbook/modules/reference.html
    Adapts typescript-eslint no-restricted-imports
    https://typescript-eslint.io/rules/no-restricted-imports/
    Cites "Clean Architecture", boundaries and dependency direction
    """
    facts = subject.facts().with_columns(
        pl.col("deepest_relative_import").cast(pl.UInt64).alias("value")
    )
    selected = facts.filter(pl.col("value") > 0)
    return RuleQuery.integer(
        facts,
        pl.col("value"),
        findings=FindingQuery.build(
            selected,
            pl.concat_str(
                pl.lit("`"),
                pl.col("path"),
                pl.lit("` imports through `"),
                pl.col("deepest_relative_specifier"),
                pl.lit("`, which climbs "),
                pl.col("value"),
                pl.when(pl.col("value") == 1)
                .then(pl.lit(" directory"))
                .otherwise(pl.lit(" directories")),
                pl.lit(" out of its own"),
            ),
            (("directories it climbs", pl.col("value"), Unit.COUNT),),
            question=pl.concat_str(
                pl.lit("stop `"),
                pl.col("path"),
                pl.lit("` reaching across the tree to import"),
            ),
            options=(
                "declare a path alias for the boundary the climb crosses",
                "move whichever of the two files is in the wrong place",
            ),
            evidence=pl.col("evidence"),
        ),
    )
