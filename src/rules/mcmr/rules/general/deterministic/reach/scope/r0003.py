import polars as pl
from pydantic import NonNegativeInt

from ...... import rule
from ......domain.contracts import Unit
from ......facts import SymbolReachFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import Table
from ..relations import ReachTables


@rule("ALL-REAC0003")
def repository_wide_declaration(
    subject: Table[SymbolReachFact], *, maximum_packages: NonNegativeInt = 3
) -> CountQuery:
    """Count declarations whose use spreads across more packages than a contract should.

    Definition
    ----------
    Report a declaration that more than `maximum_packages` distinct top-level packages reach. A
    name used that widely is load-bearing whether or not anyone declared it so, because every
    package that reaches it now depends on its exact shape, and changing it means changing all of
    them at once.

    Spread is not a defect. It is the evidence that tells a project which declarations are its real
    contracts, so those can be documented, versioned, and tested as contracts rather than
    discovered during a refactor.

    Evidence
    --------
    Each finding names the declaration and the packages, directories, and files that reach it. The
    value is the number of declarations spreading past the configured width.

    Exceptions
    ----------
    A shared foundation is supposed to spread. A base model, a logger, and a configuration reader
    are wide by design, and a project raises the ceiling or excludes the module that owns them. A
    declaration reached from only one package, however many files that package holds, is local to
    that package and is not counted.

    Examples
    --------
    A `Model` base class reached from six packages returns `1` and deserves a stated contract. A
    helper reached from four files of one package returns `0`.

    References
    ----------
    Cites "Clean Architecture", the stable dependencies principle
    Cites "Agile Software Development", the common closure principle
    Cites "A Philosophy of Software Design", on deep modules
    """
    relations = ReachTables(subject)
    selected = relations.declarations().filter(pl.col("referencing_packages") > maximum_packages)
    frame = relations.counted(selected)
    findings = FindingQuery.build(
        relations.finding_rows(selected),
        pl.concat_str(
            pl.lit("`"),
            pl.col("qualname"),
            pl.lit("` is reached from "),
            pl.col("referencing_packages"),
            pl.lit(" packages, "),
            pl.col("referencing_directories"),
            pl.lit(" directories, and "),
            pl.col("referencing_files"),
            pl.lit(" files"),
        ),
        (
            ("packages reaching it", pl.col("referencing_packages"), Unit.COUNT),
            ("directories reaching it", pl.col("referencing_directories"), Unit.COUNT),
            ("files reaching it", pl.col("referencing_files"), Unit.COUNT),
        ),
        finding_order=pl.col("ordinal"),
        evidence=pl.col("evidence"),
    )
    return RuleQuery.integer(frame, pl.col("value"), findings=findings)
