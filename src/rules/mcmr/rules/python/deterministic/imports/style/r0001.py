import polars as pl

from ...... import rule
from ......domain.contracts import FixSafety
from ......facts import ImportBindingFact
from ......query import FindingQuery, FixQuery, RuleQuery
from ......table import ImportBindingRelation, Table


def _relative_modules(frame: pl.LazyFrame, selected: pl.Expr) -> pl.LazyFrame:
    """Resolve the shortest relative module spelling for each selected import."""
    parts = (
        frame.filter(selected & (pl.col("importer_module") != ""))
        .with_columns(
            pl.col("importer_module")
            .str.split(".")
            .list.slice(0, pl.col("importer_module").str.split(".").list.len() - 1)
            .alias("package_parts"),
            pl.col("module").str.split(".").alias("target_parts"),
        )
        .with_columns(
            pl.col("package_parts").list.len().alias("package_length"),
            pl.col("target_parts").list.len().alias("target_length"),
            pl.min_horizontal(
                pl.col("package_parts").list.len(),
                pl.col("target_parts").list.len(),
            ).alias("shared_limit"),
        )
    )
    mismatches = (
        parts.select(
            "fact_id",
            "package_parts",
            "target_parts",
            pl.int_ranges(0, "shared_limit", dtype=pl.UInt64).alias("part_index"),
        )
        .explode("part_index", empty_as_null=True)
        .filter(
            pl.col("package_parts").list.get("part_index")
            != pl.col("target_parts").list.get("part_index")
        )
        .group_by("fact_id")
        .agg(pl.col("part_index").min().alias("first_mismatch"))
    )
    relative_parts = (
        parts.join(mismatches, on="fact_id", how="left")
        .with_columns(pl.coalesce("first_mismatch", "shared_limit").alias("shared_length"))
        .with_columns(
            pl.lit("")
            .str.pad_start(pl.col("package_length") - pl.col("shared_length") + 1, ".")
            .alias("dots")
        )
    )
    target_suffixes = (
        relative_parts.select(
            "fact_id",
            "target_parts",
            pl.int_ranges("shared_length", "target_length", dtype=pl.UInt64).alias("suffix_index"),
        )
        .explode("suffix_index", empty_as_null=True)
        .drop_nulls("suffix_index")
        .with_columns(pl.col("target_parts").list.get("suffix_index").alias("suffix_part"))
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("suffix_part").sort_by("suffix_index").str.join(".").alias("target_suffix"))
    )
    return relative_parts.join(target_suffixes, on="fact_id", how="left").with_columns(
        pl.concat_str(pl.col("dots"), pl.col("target_suffix").fill_null("")).alias(
            "relative_module"
        )
    )


def _replacement_rows(relative: pl.LazyFrame) -> pl.LazyFrame:
    """Build binding-preserving module and declaration replacements."""
    module_replacement = relative.filter(
        (pl.col("imported_name") != pl.col("module")) & (pl.col("module_node_id") != "")
    ).select(
        "fact_id",
        pl.lit("module").alias("target_role"),
        pl.col("relative_module").alias("source"),
    )
    parent_modules = (
        relative.select(
            "fact_id",
            pl.int_ranges(
                "shared_length",
                pl.col("target_length") - 1,
                dtype=pl.UInt64,
            ).alias("parent_index"),
            "target_parts",
        )
        .explode("parent_index", empty_as_null=True)
        .drop_nulls("parent_index")
        .with_columns(pl.col("target_parts").list.get("parent_index").alias("parent_part"))
        .group_by("fact_id")
        .agg(pl.col("parent_part").sort_by("parent_index").str.join(".").alias("parent_module"))
    )
    declaration_replacement = (
        relative.join(parent_modules, on="fact_id", how="left")
        .filter(
            (pl.col("imported_name") == pl.col("module"))
            & (pl.col("name") != pl.col("target_parts").list.first())
            & (pl.col("declaration_id") != "")
            & (pl.col("target_length") > pl.col("shared_length"))
        )
        .select(
            "fact_id",
            pl.lit("declaration").alias("target_role"),
            pl.concat_str(
                pl.lit("from "),
                pl.col("dots"),
                pl.col("parent_module").fill_null(""),
                pl.lit(" import "),
                pl.col("target_parts").list.last(),
                pl.lit(" as "),
                pl.col("name"),
            ).alias("source"),
        )
    )
    return pl.concat([module_replacement, declaration_replacement], how="vertical")


@rule("PY-IMPO0001", fix_safety=FixSafety.SAFE)
def internal_relative_import(
    subject: Table[ImportBindingFact],
) -> RuleQuery[bool]:
    """Detect an absolute import of a module owned by the current project package.

    Definition
    ----------
    Index Python modules below the configured source roots, including namespace-package prefixes
    that have no `__init__.py`. Inspect selected files for absolute `import` and `from` statements
    whose resolved module belongs to the same top-level project package as the importing module.
    Derive the relative level from the current package and longest common dotted prefix. The
    Boolean result identifies one qualifying statement. The default policy prefers relative
    imports.

    Evidence
    --------
    Each finding records the imported project modules and source range. A safe UTF-8 text edit is
    attached when the statement is single-line, the relative level is unique, and all local names
    remain unchanged. Aliased module imports can be rewritten as `from` imports. Unaliased dotted
    imports are reported without an edit because they bind the package root rather than the final
    module name.

    Exceptions
    ----------
    Keep absolute imports across different top-level packages, for unresolved modules, or when a
    public executable intentionally supports direct invocation outside its package. Relative
    imports already in use, wildcard imports, standalone top-level modules, mixed import lists,
    ignored files receive no fact from discovery and therefore no automatic edit. Package-root
    `from` imports are supported, while a bare `import package` has no binding-preserving relative
    equivalent.

    Examples
    --------
    Bad
    ~~~
    Inside `acme/features/service.py`, `from acme.models import User` and
    `import acme.tools.formatting as formatting` are internal absolute imports.

    Good
    ~~~~
    `from ...models import User`, `from ...tools import formatting as formatting`, and
    `import httpx` preserve an explicit package boundary.

    References
    ----------
    Cites "PEP 328, Imports and Relative Imports"
    https://peps.python.org/pep-0328/
    Cites "The Python Language Reference", the import statement
    https://docs.python.org/3.14/reference/simple_stmts.html#the-import-statement
    Cites "The Python Language Reference", Namespace packages
    https://docs.python.org/3.14/reference/import.html#namespace-packages
    """
    frame = subject.lazy(ImportBindingRelation.FACTS)
    value = pl.col("is_project_owned") & ~pl.col("is_relative") & ~pl.col("is_wildcard")
    relative = _relative_modules(frame, value)
    replacements = _replacement_rows(relative)
    rewrites = replacements.select(
        "fact_id",
        pl.lit(0, dtype=pl.UInt64).alias("rewrite_order"),
        pl.lit("replace").alias("kind"),
        "source",
        pl.lit("").alias("placement"),
        pl.lit("").alias("name"),
        pl.lit("").alias("symbol_id"),
        pl.lit("").alias("symbol_name"),
        pl.lit(False).alias("references_complete"),
    )
    nodes = (
        subject.lazy(ImportBindingRelation.NODES)
        .join(
            replacements,
            left_on=["fact_id", "role"],
            right_on=["fact_id", "target_role"],
            how="inner",
        )
        .select(
            "fact_id",
            pl.lit(0, dtype=pl.UInt64).alias("rewrite_order"),
            pl.lit("target").alias("role"),
            pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
            pl.col("node_id").alias("id"),
            "path",
            "start_line",
            "start_column",
            "end_line",
            "end_column",
            "kind",
            "text",
        )
    )
    fix = FixQuery.build(
        "State the same module through the shortest equivalent relative path.",
        rewrites=rewrites,
        nodes=nodes,
    )
    return RuleQuery.boolean(
        frame,
        value,
        findings=FindingQuery.precise_boolean(frame, value, "internal relative import"),
        fix=fix,
    )
