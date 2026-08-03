import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import SymbolReachFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import Table
from ..relations import ReachTables

# Only module-scope names have complete reach evidence. Untyped receivers and property reads keep
# methods outside this rule.
_REACHABLE_KINDS = ["class", "function"]


@rule("ALL-REAC0002")
def file_local_public_declaration(subject: Table[SymbolReachFact]) -> CountQuery:
    """Count public declarations only their own file ever uses.

    Definition
    ----------
    Report a public declaration that at least one reference reaches, where every one of those
    references sits in the file that declares it. A name published to the whole repository but
    used in exactly one place is stating a contract it does not have. Making it nonpublic tells a
    reader the truth, and it frees the declaration to change without a repository-wide search.

    This is the ordinary way a module accumulates surface. A helper is written public because
    everything else nearby is public, and nothing ever calls it from outside.

    Evidence
    --------
    Each finding names the declaration, its kind, and how many references its own file makes
    against the nothing every other file makes. The repair is a choice, because a name is either
    an interface nobody adopted yet or a helper that was never meant to be one. The value is the
    number of such declarations.

    Exceptions
    ----------
    A module a test runner collects is skipped, since its declarations are reached by name. A
    published API, a framework hook, and a plugin entry point are reached from outside the
    repository, so their reference counts understate them. A declaration a test file reaches is
    reached from another file and is not counted here.

    Examples
    --------
    A public `def parse_header(line)` that only its own module calls returns `1` and should become
    `_parse_header` or move inside its single caller. The same function called from two modules
    returns `0`.

    References
    ----------
    Cites "PEP 8, Style Guide for Python Code", public and internal interfaces
    https://peps.python.org/pep-0008/#public-and-internal-interfaces
    Cites "A Philosophy of Software Design", on narrow interfaces
    Cites "Effective Go", names and exported identifiers
    https://go.dev/doc/effective_go#names
    """
    relations = ReachTables(subject)
    selected = relations.declarations().filter(
        ~pl.col("is_test_module")
        & pl.col("is_module_scope")
        & ~pl.col("is_decorated")
        & pl.col("kind").is_in(_REACHABLE_KINDS)
        & (pl.col("visibility") == "public")
        & (pl.col("own_file_references") > 0)
        & (pl.col("other_file_references") == 0)
    )
    frame = relations.counted(selected)
    own_count = pl.concat_str(
        pl.col("own_file_references"),
        pl.when(pl.col("own_file_references") == 1)
        .then(pl.lit(" time"))
        .otherwise(pl.lit(" times")),
    )
    findings = FindingQuery.build(
        relations.finding_rows(selected),
        pl.concat_str(
            pl.lit("`"),
            pl.col("qualname"),
            pl.lit("` is a public "),
            pl.col("kind"),
            pl.lit(" read "),
            own_count,
            pl.lit(" inside this file and nowhere outside it"),
        ),
        (
            ("references from its own file", pl.col("own_file_references"), Unit.COUNT),
            ("references from anywhere else", pl.lit(0), Unit.COUNT),
        ),
        finding_order=pl.col("ordinal"),
        question=pl.concat_str(pl.lit("say what `"), pl.col("qualname"), pl.lit("` is for")),
        options=(
            "make it private, since nothing outside reads it",
            "keep it public where it is an interface this file publishes",
        ),
        evidence=pl.col("evidence"),
    )
    return RuleQuery.integer(frame, pl.col("value"), findings=findings)
