import polars as pl

from ..... import rule
from .....domain.contracts import Unit
from .....facts import ModuleSurfaceFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table import Table


@rule("TS-MODU0001")
def star_reexport_surface(subject: Table[ModuleSurfaceFact]) -> CountQuery:
    """Count the wholesale re-exports that turn a module's internals into its public API.

    Definition
    ----------
    Count `export *` declarations in one module. Each one publishes everything the file it names
    happens to export, now and after every future edit. A helper added for one caller becomes part
    of the module's contract the moment it is exported, and no reviewer sees that happen. The
    module then cannot be refactored safely, because nobody knows which of its internals somebody
    outside came to depend on.

    A barrel that names its exports states a contract. A barrel that stars them states a wish.

    Evidence
    --------
    Each finding names one wholesale re-export and the module it publishes, counted against the
    named exports beside it so a reader can see how much of the surface is stated and how much is
    inherited. The repair is a choice, since naming the exports and declaring the barrel a real
    public API are both real answers. The value is the number of wholesale re-exports.

    Exceptions
    ----------
    A package root that deliberately re-publishes a subpackage is a real public API and belongs in
    a project's exclusions. A generated index is regenerated rather than edited, so a project
    excludes the generator's output instead of the generator.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: typescript

       export * from './UserService';
       export * from './internal/userValidation';

    Good
    ~~~~
    .. code-block:: typescript

       export { UserService } from './services/UserService';
       export type { UserDTO } from './dto/UserDTO';

    References
    ----------
    Cites "TypeScript documentation", handbook, modules and re-exports
    https://www.typescriptlang.org/docs/handbook/2/modules.html
    Cites "typescript-eslint documentation", no-restricted-imports and module boundary guidance
    https://typescript-eslint.io/rules/no-restricted-imports/
    Cites "eslint-plugin-boundaries documentation", declaring allowed import directions
    https://github.com/javierbrea/eslint-plugin-boundaries
    """
    relations = subject
    facts = relations.facts().with_columns(
        pl.col("star_reexports.length").cast(pl.UInt64).alias("value")
    )
    selected = relations.values("star_reexports").join(
        facts,
        on=["fact_order", "fact_id"],
        how="inner",
    )
    return RuleQuery.integer(
        facts,
        pl.col("value"),
        findings=FindingQuery.build(
            selected,
            pl.concat_str(
                pl.lit("`"),
                pl.col("path"),
                pl.lit("` re-exports everything `"),
                pl.col("string_value"),
                pl.lit(
                    "` happens to export, so a helper added there joins this module's contract "
                    "unreviewed"
                ),
            ),
            (
                ("wholesale re-exports", pl.col("value"), Unit.COUNT),
                (
                    "named re-exports beside them",
                    pl.col("named_reexport_count"),
                    Unit.COUNT,
                ),
            ),
            finding_order=pl.col("ordinal"),
            question=pl.concat_str(
                pl.lit("say what `"),
                pl.col("path"),
                pl.lit("` means to publish from `"),
                pl.col("string_value"),
                pl.lit("`"),
            ),
            options=(
                "name the exports this module actually offers",
                "exclude a package root that deliberately republishes a subpackage",
            ),
            evidence=pl.col("evidence"),
        ),
    )
