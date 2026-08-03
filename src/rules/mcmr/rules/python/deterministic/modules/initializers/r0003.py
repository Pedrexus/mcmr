import polars as pl

from ...... import rule
from ......domain.contracts import FixSafety
from ......facts import CallFact, ClassFact, FunctionFact, ImportBindingFact, ModuleFact
from ......query import CountQuery, FindingQuery, FixQuery, RuleQuery
from ......table import CallRelation, ClassRelation, FunctionRelation, ImportBindingRelation, Table


@rule("PY-MODU0003", fix_safety=FixSafety.REVIEW)
def initializer_declaration(
    subject: Table[ModuleFact],
    functions: Table[FunctionFact],
    calls: Table[CallFact],
    classes: Table[ClassFact],
    imports: Table[ImportBindingFact],
) -> CountQuery:
    """Reject ordinary function and class declarations in package initializers.

    Definition
    ----------
    Count every top-level class and every ordinary top-level function declared in `__init__.py`.
    Package initializers state a package surface and leave implementation declarations in focused
    sibling modules. Python module customization hooks remain valid declarations because the
    language invokes them on the module itself.

    Evidence
    --------
    Each finding covers one initializer and records its exact disallowed declaration count. The
    value is `0` when the initializer contains only surface declarations and supported hooks.

    Exceptions
    ----------
    The module hooks `__getattr__` and `__dir__` are accepted as specified by Python. Imported
    functions and classes are not declarations in the initializer and remain accepted.

    Examples
    --------
    Bad
    ~~~
    `class Client` or `def connect()` declared directly in `__init__.py` returns `1`.

    Good
    ~~~~
    `def __getattr__(name)` in `__init__.py` returns `0`, as does an imported `Client`.

    References
    ----------
    Cites "PEP 562, Module __getattr__ and __dir__"
    https://peps.python.org/pep-0562/
    Cites "The Python Language Reference", customizing module attribute access
    https://docs.python.org/3.14/reference/datamodel.html#customizing-module-attribute-access
    """
    initializers = (
        subject.facts().filter(pl.col("is_package_initializer")).select("fact_id", "path")
    )
    initializer_paths = initializers.rename({"fact_id": "module_fact_id"})
    disallowed = (
        subject.records("members")
        .join(
            initializers,
            on="fact_id",
            how="inner",
        )
        .filter(
            (pl.col("kind") == "class")
            | ((pl.col("kind") == "function") & ~pl.col("name").is_in(["__getattr__", "__dir__"]))
        )
    )
    frame = subject.counted(disallowed)
    candidates = (
        functions.lazy(FunctionRelation.FUNCTIONS)
        .filter(
            (pl.col("scope") == "module")
            & ~pl.col("name").is_in(["__getattr__", "__dir__"])
            & pl.col("definition_id").is_not_null()
        )
        .join(initializer_paths, left_on="definition_path", right_on="path", how="inner")
        .rename({"entity_id": "function_id"})
    )
    contained_calls = (
        calls.lazy(CallRelation.CALLS)
        .filter(pl.col("is_constructor") & pl.col("is_first_party"))
        .join(candidates, left_on="node_path", right_on="definition_path", how="inner")
        .with_columns(pl.col("node_path").alias("definition_path"))
        .filter(
            (
                (pl.col("node_start_line") > pl.col("definition_start_line"))
                | (
                    (pl.col("node_start_line") == pl.col("definition_start_line"))
                    & (pl.col("node_start_column") >= pl.col("definition_start_column"))
                )
            )
            & (
                (pl.col("node_end_line") < pl.col("definition_end_line"))
                | (
                    (pl.col("node_end_line") == pl.col("definition_end_line"))
                    & (pl.col("node_end_column") <= pl.col("definition_end_column"))
                )
            )
        )
        .with_columns(
            pl.col("qualified_name").str.split(".").list.last().alias("owner_name"),
            pl.col("qualified_name").n_unique().over("function_id").alias("destination_count"),
            pl.col("definition_path").str.extract(r"^(.*)/[^/]+$", 1).alias("source_parent"),
        )
        .filter(pl.col("destination_count") == 1)
        .unique(subset=["function_id"], maintain_order=True)
    )
    owners = (
        classes.lazy(ClassRelation.CLASSES)
        .filter(pl.col("scope") == "module")
        .select(
            pl.col("class_id").alias("anchor_id"),
            pl.col("name").alias("owner_name"),
            pl.col("path").alias("anchor_path"),
            pl.col("start_line").alias("anchor_start_line"),
            pl.col("start_column").alias("anchor_start_column"),
            pl.col("end_line").alias("anchor_end_line"),
            pl.col("end_column").alias("anchor_end_column"),
            pl.lit("class").alias("anchor_kind"),
            pl.col("source").alias("anchor_text"),
            pl.col("path").str.extract(r"^(.*)/[^/]+$", 1).alias("anchor_parent"),
        )
    )
    fixable = (
        contained_calls.join(owners, on="owner_name", how="inner")
        .filter(
            (pl.col("anchor_parent") == pl.col("source_parent"))
            & (pl.col("anchor_path") != pl.col("definition_path"))
        )
        .with_columns(pl.col("anchor_id").n_unique().over("function_id").alias("owner_count"))
        .filter(pl.col("owner_count") == 1)
        .unique(subset=["function_id"], maintain_order=True)
        .with_columns(
            pl.col("function_id").n_unique().over("module_fact_id").alias("fixable_count")
        )
        .join(
            frame.select("fact_id", "value"),
            left_on="module_fact_id",
            right_on="fact_id",
            how="inner",
        )
        .filter(pl.col("fixable_count") == pl.col("value"))
        .with_columns(
            (
                pl.col("definition_start_line")
                .rank("ordinal")
                .over("module_fact_id")
                .sub(1)
                .cast(pl.UInt64)
            ).alias("rewrite_order")
        )
    )
    rewrites = fixable.select(
        pl.col("module_fact_id").alias("fact_id"),
        "rewrite_order",
        pl.lit("move").alias("kind"),
        pl.lit("").alias("source"),
        pl.lit("after").alias("placement"),
        pl.lit("").alias("name"),
        pl.lit("").alias("symbol_id"),
        pl.lit("").alias("symbol_name"),
        pl.lit(False).alias("references_complete"),
    )
    nodes = pl.concat(
        [
            fixable.select(
                pl.col("module_fact_id").alias("fact_id"),
                "rewrite_order",
                pl.lit(role).alias("role"),
                pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
                pl.col(f"{prefix}_id").alias("id"),
                pl.col(f"{prefix}_path").alias("path"),
                pl.col(f"{prefix}_start_line").cast(pl.UInt64).alias("start_line"),
                pl.col(f"{prefix}_start_column").cast(pl.UInt64).alias("start_column"),
                pl.col(f"{prefix}_end_line").cast(pl.UInt64).alias("end_line"),
                pl.col(f"{prefix}_end_column").cast(pl.UInt64).alias("end_column"),
                pl.col(f"{prefix}_kind").alias("kind"),
                pl.col(f"{prefix}_text").alias("text"),
            )
            for role, prefix in (("target", "definition"), ("anchor", "anchor"))
        ]
    )
    references = (
        imports.lazy(ImportBindingRelation.NODES)
        .filter(pl.col("role") == "reference")
        .rename({"fact_id": "import_fact_id", "path": "reference_path"})
        .join(fixable, left_on="reference_path", right_on="definition_path", how="inner")
        .with_columns(
            (
                (
                    (pl.col("start_line") > pl.col("definition_start_line"))
                    | (
                        (pl.col("start_line") == pl.col("definition_start_line"))
                        & (pl.col("start_column") >= pl.col("definition_start_column"))
                    )
                )
                & (
                    (pl.col("end_line") < pl.col("definition_end_line"))
                    | (
                        (pl.col("end_line") == pl.col("definition_end_line"))
                        & (pl.col("end_column") <= pl.col("definition_end_column"))
                    )
                )
            ).alias("inside_definition")
        )
        .group_by("module_fact_id", "function_id", "rewrite_order", "import_fact_id")
        .agg(
            pl.len().cast(pl.UInt64).alias("exact_reference_count"),
            pl.col("inside_definition").all(),
            pl.col("qualified_name").first(),
        )
    )
    import_requests = (
        imports.lazy(ImportBindingRelation.FACTS)
        .rename({"fact_id": "import_fact_id"})
        .join(references, on="import_fact_id", how="inner")
        .filter(
            pl.col("inside_definition")
            & (pl.col("reference_count") == pl.col("exact_reference_count"))
            & (pl.col("name") != pl.col("qualified_name").str.split(".").list.last())
        )
        .with_columns(pl.col("declaration_text").str.starts_with("from ").alias("is_from"))
        .select(
            pl.col("module_fact_id").alias("fact_id"),
            "rewrite_order",
            pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
            "module",
            pl.when(pl.col("is_from"))
            .then(pl.col("imported_name"))
            .otherwise(pl.lit(""))
            .alias("name"),
            pl.when(
                pl.col("name")
                != pl.when(pl.col("is_from"))
                .then(pl.col("imported_name"))
                .otherwise(pl.col("module").str.split(".").list.first())
            )
            .then(pl.col("name"))
            .otherwise(pl.lit(""))
            .alias("alias"),
            pl.col("relative_level").cast(pl.UInt64).alias("level"),
            pl.col("is_type_only").alias("type_only"),
        )
    )
    return RuleQuery.integer(
        frame,
        pl.col("value"),
        findings=FindingQuery.precise_integer(frame, pl.col("value"), "initializer declaration"),
        fix=FixQuery.build(
            "Move every initializer implementation beside its one proven constructed owner.",
            rewrites=rewrites,
            nodes=nodes,
            imports=import_requests,
        ),
    )
