from collections.abc import Sequence

import polars as pl

from ..... import Numeric, rule
from .....facts import DirectoryFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table import Table


@rule("ALL-FILE0002", policy=Numeric(maximum=5))
def package_depth(
    subject: Table[DirectoryFact],
    *,
    framework_roots: Sequence[str] = (),
) -> CountQuery:
    """Measure how deep below a source root one directory of modules sits.

    Definition
    ----------
    Take the repository-relative path of this directory, remove the longest source root that
    prefixes it, and count the directory levels that remain. A module six directories below a
    source root costs every reader an import line that says nothing and a search path nobody
    remembers, and the depth is what says so before anybody has to navigate it.

    A source root is read off the tree rather than configured, which is any directory named `src`
    together with the first ancestor of a package chain that is not itself a package, so a Python
    import root and a Rust crate source directory both count as one. Where no source root prefixes
    the directory, the count runs from the repository root instead, so a project laid out flat
    still gets a comparable number. Depth alone does not prove poor architecture, which is why the
    rule states the depth and a project policy owns the ceiling.

    Evidence
    --------
    The finding names the repository-relative directory the walk met. The value is the number of
    directory levels between this directory and the source root above it, which is zero for a
    source root itself and zero for the repository root.

    Exceptions
    ----------
    A namespace package, a generated API tree, a framework-imposed layout, and a deliberately
    layered rule catalog can name their exact implementation roots through `framework_roots`.
    Those trees are outside this population because their public facade, rather than their storage
    path, owns navigation depth. This measure balances the separate ceiling on direct modules per
    directory, since driving either one down alone pushes the other up.

    Examples
    --------
    `src/shop/orders/commands` measures `3`, because `src` is a source root and three levels remain
    below it. A `shop/orders/commands` directory in a repository that names no source root measures
    `3` as well, counted from the repository root, and one more level below it measures `4`. A
    `src/core/src` directory measures `0`, being a source root itself, and the repository root
    measures `0` too.

    References
    ----------
    Cites "Python Packaging User Guide", src layout
    https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/
    Cites "A Philosophy of Software Design", information hiding and navigation cost
    """
    excluded = (
        pl.any_horizontal(
            [
                (pl.col("path") == root) | pl.col("path").str.starts_with(f"{root.rstrip('/')}/")
                for root in framework_roots
            ]
        )
        if framework_roots
        else pl.lit(False)
    )
    frame = subject.facts().filter(~excluded)
    value = pl.col("source_depth")
    return RuleQuery.integer(
        frame,
        value,
        findings=FindingQuery.precise_integer(
            frame,
            value,
            "package depth",
            evidence=pl.col("evidence"),
        ),
    )
