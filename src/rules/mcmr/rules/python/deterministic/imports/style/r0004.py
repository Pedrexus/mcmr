import polars as pl

from ...... import rule
from ......facts import ImportBindingFact
from ......query import FindingQuery, RuleQuery
from ......table import ImportBindingRelation, Table


@rule("PY-IMPO0004")
def relative_import_beyond_package(
    subject: Table[ImportBindingFact],
) -> RuleQuery[bool]:
    """Report a relative import climbing past the top-level package it starts in.

    Definition
    ----------
    Count the leading dots one relative import states and compare them against the package holding
    the importing module. One dot names that package, two name its parent, and an import stating
    more dots than the package has components leaves the tree entirely and raises `ImportError`
    the first time the module loads. A package initializer is its own package, so it affords one
    more level than a module sitting beside it.

    This needs no interpreter and no installed environment. Both halves of the comparison, the
    dots in the statement and the package derived from the file layout, are in the repository, so
    the answer is arithmetic rather than a resolution attempt.

    Evidence
    --------
    The finding names the import and the module stating it. The result reports whether the import
    reaches above the top-level package.

    Exceptions
    ----------
    A module in no package at all is not judged. There is no top level for it to exceed, the
    interpreter answers with a different failure, and the file is usually a script rather than
    part of a tree. A dot count within the package is correct however deep it goes, since depth is
    a separate question the relative-import-depth rule already asks.

    Examples
    --------
    Bad
    ~~~
    `from ...shared import Client` inside `pkg/sub/module.py`, whose package `pkg.sub` has two
    components, climbs one level above `pkg`.

    Good
    ~~~~
    `from ..shared import Client` inside `pkg/sub/module.py` reaches `pkg.shared`, which exists.

    References
    ----------
    Generalizes Pylint E0402 relative-beyond-top-level
    https://pylint.readthedocs.io/en/latest/user_guide/messages/error/relative-beyond-top-level.html
    Cites "PEP 328, Imports and Relative Imports", which defines what a leading dot counts against
    https://peps.python.org/pep-0328/
    Cites "The CPython source", the check this reproduces
    https://docs.python.org/3/reference/import.html#package-relative-imports
    """
    frame = subject.lazy(ImportBindingRelation.FACTS)
    stated = pl.col("declaration_text").str.replace(r"^from ", "")
    level = stated.str.len_chars() - stated.str.strip_chars_start(".").str.len_chars()
    components = pl.col("importer_module").str.split(".").list.len().cast(pl.Int64)
    owned = (
        pl.when(pl.col("path").str.ends_with("__init__.py"))
        .then(components)
        .otherwise(components - 1)
    )
    value = (
        pl.col("is_relative")
        & (pl.col("declaration_text") != "")
        & (owned > 0)
        & (level.cast(pl.Int64) > owned)
    )
    return RuleQuery.boolean(
        frame,
        value,
        findings=FindingQuery.precise_boolean(frame, value, "relative import beyond package"),
    )
