import polars as pl

from ..... import Numeric, rule
from .....facts import DirectoryFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table import Table


@rule("ALL-FILE0003", policy=Numeric(maximum=3))
def directory_module_count(
    subject: Table[DirectoryFact],
    *,
    allow_definition_catalogs: bool = True,
) -> CountQuery:
    """Measure how many modules one directory holds directly.

    Definition
    ----------
    Count the source files sitting directly in this directory, whatever language wrote them.
    Modules in subdirectories belong to those subdirectories and never count toward an ancestor, so
    the number says how many files a reader opening this folder has to choose between.

    A directory whose every module declares exactly one class or one function is a catalog whose
    width is the point rather than a symptom, so `allow_definition_catalogs` measures it as zero
    and holds that exemption open by default. A package initializer is excluded from both the
    catalog judgment and the file count, since it states what the directory is rather than adding
    an implementation module a reader has to choose between. Setting the option false applies the
    raw implementation count everywhere, which is what a project wants when it does not organize
    anything that way.

    Evidence
    --------
    The finding names the repository-relative directory the walk met. The value is the number of
    source files directly inside it, or zero for a directory the provider recognized as a
    definition catalog.

    Exceptions
    ----------
    A flat plugin collection, a migrations folder, and a generated schema tree stay clear above any
    reasonable ceiling, so a project excludes them rather than splitting them. A definition catalog
    is recognized from what its modules declare rather than by directory name, which is what keeps
    the exemption from becoming a hardcoded path list. Splitting a wide directory is only a repair
    when the new folder groups one coherent concept, since a forwarding folder holding one
    unrelated module makes navigation worse. Depth below a source root is measured separately.

    Examples
    --------
    A `services` directory holding six source files returns `6`. A directory of seven modules that
    each declare one class returns `0` under the default, because it is a definition catalog, and
    `7` under `allow_definition_catalogs=False`. Four modules under `services/payments` count
    toward `services/payments` and add nothing to `services`.

    References
    ----------
    Cites "A Philosophy of Software Design", chapters 4 and 5
    Cites "Agile Software Development", package cohesion principles
    """
    frame = subject.facts().with_columns(
        pl.when(pl.lit(allow_definition_catalogs) & pl.col("is_definition_catalog"))
        .then(0)
        .otherwise(pl.col("direct_module_count"))
        .alias("value")
    )
    return RuleQuery.integer(
        frame,
        pl.col("value"),
        findings=FindingQuery.precise_integer(
            frame,
            pl.col("value"),
            "directory module count",
            evidence=pl.col("evidence"),
        ),
    )
