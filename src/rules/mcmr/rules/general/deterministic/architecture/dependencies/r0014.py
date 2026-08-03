import polars as pl

from ...... import rule
from ......facts import ModuleCouplingFact, Ratio
from ......query import FindingQuery, OccurrenceQuery, RuleQuery
from ......table import Table
from ...coupling import CouplingRelations


@rule("ALL-ARCH0005")
def abstraction_nothing_depends_on(
    subject: Table[ModuleCouplingFact],
    *,
    minimum_abstractness: Ratio = 0.5,
) -> OccurrenceQuery:
    """Report a module written as a contract that no other module in this repository imports.

    Definition
    ----------
    An abstraction earns its cost by being depended upon. Where abstractness `A` is high and
    afferent coupling is zero, nobody took the promise up, which puts the module in the far corner
    Martin calls the zone of uselessness. It is the mirror of the concrete module everything leans
    on, and it is scaffolding somebody built for a second implementation that never arrived.

    Both halves are required. Afferent coupling has to be zero, so a widely implemented base class
    is never reported, and `A` has to reach `minimum_abstractness`, so a module of plain functions
    that happens to be a leaf is left alone. Read against the main sequence this is the same
    finding as a large `D` on the abstract side, since a module nothing imports and that imports
    anything has `I` of one and therefore `D` equal to its own `A`.

    Evidence
    --------
    Each finding names the module, how many of its types are contracts, and that nothing in the
    repository imports it. The value is whether this module is an abstraction with no dependents.

    Exceptions
    ----------
    A library publishes abstractions for callers outside its own repository, and a plugin contract
    a framework loads by name is reached in a way no static graph sees, so both are legitimately
    unreferenced here and belong in the exclusion set rather than in the code that gets deleted. A
    module the tests alone implement is genuinely unused by the shipped code, which is worth
    knowing rather than worth hiding. A repository whose whole graph is unresolved reports every
    module this way, so an empty afferent count across the board is a reason to check the graph
    before acting on any single finding.

    Examples
    --------
    Bad
    ~~~
    `storage/base.py` declares one abstract `Backend` with four abstract methods, one file
    implements it, and that file imports the concrete class directly rather than the base. `A` is
    `1.0` and nothing imports the module. The contract exists to be swapped and nothing swaps.
    This returns `true`.

    Good
    ~~~~
    `storage/base.py` declares the same `Backend`, and six modules import it to type their
    parameters against it. This returns `false`, whatever the implementations look like.

    References
    ----------
    Cites "Agile Software Development", the zone of uselessness
    Cites "Clean Architecture", chapter 14, component coupling
    Cites "Design Principles and Design Patterns"
    https://web.archive.org/web/20150906155800/http://www.objectmentor.com/resources/articles/Principles_and_Patterns.pdf
    Cites "Extreme Programming Explained", you are not going to need it
    """
    frame = (
        CouplingRelations(subject)
        .modules()
        .with_columns(
            (
                (pl.col("afferent_count") == 0) & (pl.col("abstractness") >= minimum_abstractness)
            ).alias("value")
        )
    )
    return RuleQuery.boolean(
        frame,
        pl.col("value"),
        findings=FindingQuery.precise_boolean(
            frame,
            pl.col("value"),
            "abstraction nothing depends on",
            evidence=pl.col("evidence"),
        ),
    )
