import polars as pl

from ....domain.contracts import Unit
from ....facts import SymbolFact
from ....query import CountQuery, FindingQuery, FixQuery, RuleQuery
from ....table.relations import FactRelations


class SymbolRelations(FactRelations[SymbolFact]):
    """Expose resolved symbols and scoped typing declarations."""

    def definitions(self) -> pl.LazyFrame:
        """Return every typing declaration located in source."""
        return self.records("typing_scopes.definitions").select(
            "fact_order",
            "fact_id",
            "record_id",
            pl.col("parent_id").alias("scope_id"),
            pl.col("ordinal").alias("definition_ordinal"),
            "name",
            pl.col("span.path").alias("path"),
            pl.col("span.start_line").cast(pl.UInt64).alias("start_line"),
            pl.col("span.start_column").cast(pl.UInt64).alias("start_column"),
            pl.col("span.end_line").cast(pl.UInt64).alias("end_line"),
            pl.col("span.end_column").cast(pl.UInt64).alias("end_column"),
        )

    def references(self) -> pl.LazyFrame:
        """Return every resolved reference node under its symbol record."""
        return self.records("symbols.reference.references").select(
            "fact_id",
            "parent_id",
            "ordinal",
            "id",
            pl.col("span.path").alias("path"),
            pl.col("span.start_line").cast(pl.UInt64).alias("start_line"),
            pl.col("span.start_column").cast(pl.UInt64).alias("start_column"),
            pl.col("span.end_line").cast(pl.UInt64).alias("end_line"),
            pl.col("span.end_column").cast(pl.UInt64).alias("end_column"),
            "kind",
            "text",
        )

    def scopes(self) -> pl.LazyFrame:
        """Return typing scopes beside aggregate reuse counts."""
        imports = (
            self.records("typing_scopes.reused_definitions")
            .group_by("fact_id", "parent_id", maintain_order=True)
            .agg(
                pl.col("importing_spans.length")
                .fill_null(0)
                .sum()
                .cast(pl.UInt64)
                .alias("cross_module_import_count")
            )
        )
        scopes = self.records("typing_scopes").select(
            "fact_order",
            "fact_id",
            pl.col("record_id").alias("scope_id"),
            pl.col("ordinal").alias("scope_ordinal"),
            pl.col("path").alias("scope_path"),
            pl.col("definitions.length").alias("definition_count"),
            pl.col("reused_definitions.length").alias("reused_definition_count"),
        )
        facts = self.facts().select("fact_order", "fact_id", "evidence")
        return (
            scopes.join(
                imports,
                left_on=["fact_id", "scope_id"],
                right_on=["fact_id", "parent_id"],
                how="left",
            )
            .join(facts, on=["fact_order", "fact_id"], how="inner")
            .with_columns(pl.col("cross_module_import_count").fill_null(0))
        )

    def symbols(self) -> pl.LazyFrame:
        """Return symbols located at a declaration when one was resolved."""
        facts = self.facts().select(
            "fact_order",
            "fact_id",
            pl.col("path").alias("fact_path"),
            pl.col("start_line").alias("fact_start_line"),
            pl.col("start_column").alias("fact_start_column"),
            pl.col("end_line").alias("fact_end_line"),
            pl.col("end_column").alias("fact_end_column"),
            "language",
            "evidence",
        )
        symbols = self.records("symbols").select(
            "fact_order",
            "fact_id",
            "record_id",
            "ordinal",
            "name",
            "scope",
            "is_constant_assignment",
            "returns_boolean",
            "reference.id",
            "reference.name",
            "reference.are_references_complete",
            "reference.references.length",
            "reference.declaration.id",
            "reference.declaration.kind",
            "reference.declaration.text",
            "reference.declaration.span.path",
            "reference.declaration.span.start_line",
            "reference.declaration.span.start_column",
            "reference.declaration.span.end_line",
            "reference.declaration.span.end_column",
        )
        resolved = pl.col("reference.id").is_not_null()
        return symbols.join(facts, on=["fact_order", "fact_id"], how="inner").with_columns(
            pl.when(resolved)
            .then(pl.col("reference.declaration.span.path"))
            .otherwise(pl.col("fact_path"))
            .alias("path"),
            pl.when(resolved)
            .then(pl.col("reference.declaration.span.start_line"))
            .otherwise(pl.col("fact_start_line"))
            .cast(pl.UInt64)
            .alias("start_line"),
            pl.when(resolved)
            .then(pl.col("reference.declaration.span.start_column"))
            .otherwise(pl.col("fact_start_column"))
            .cast(pl.UInt64)
            .alias("start_column"),
            pl.when(resolved)
            .then(pl.col("reference.declaration.span.end_line"))
            .otherwise(pl.col("fact_end_line"))
            .cast(pl.UInt64)
            .alias("end_line"),
            pl.when(resolved)
            .then(pl.col("reference.declaration.span.end_column"))
            .otherwise(pl.col("fact_end_column"))
            .cast(pl.UInt64)
            .alias("end_column"),
            pl.col("reference.references.length").fill_null(0).alias("reference_count"),
        )

    def typing_placements(self) -> pl.LazyFrame:
        """Join each typing declaration to its scope and proven importing modules."""
        reused = self.records("typing_scopes.reused_definitions").select(
            "fact_id",
            pl.col("parent_id").alias("scope_id"),
            pl.col("record_id").alias("reuse_id"),
            "name",
            pl.col("span.path").alias("path"),
        )
        importers = (
            self.records("typing_scopes.reused_definitions.importing_spans")
            .group_by("fact_id", "parent_id", maintain_order=True)
            .agg(pl.col("path").sort_by("ordinal").alias("importing_modules"))
        )
        reuse = reused.join(
            importers,
            left_on=["fact_id", "reuse_id"],
            right_on=["fact_id", "parent_id"],
            how="left",
        ).select("fact_id", "scope_id", "name", "path", "importing_modules")
        languages = self.facts().select("fact_id", "language")
        return (
            self.definitions()
            .join(self.scopes(), on=["fact_order", "fact_id", "scope_id"], how="inner")
            .join(reuse, on=["fact_id", "scope_id", "name", "path"], how="left")
            .join(languages, on="fact_id", how="inner")
            .with_columns(
                pl.col("importing_modules").fill_null(pl.lit([], dtype=pl.List(pl.String)))
            )
        )


def public_constant_query(subject: SymbolRelations) -> CountQuery:
    """Count public uppercase module constants exactly as Python does."""
    name = pl.col("name")
    uppercase = (name.str.to_uppercase() == name) & (name.str.to_lowercase() != name)
    selected = subject.symbols().filter(
        (pl.col("scope") == "module")
        & pl.col("is_constant_assignment")
        & uppercase
        & ~name.str.starts_with("_")
    )
    frame = subject.counted(selected)
    return RuleQuery.integer(
        frame,
        pl.col("value"),
        findings=FindingQuery.build(
            selected,
            pl.concat_str(
                pl.lit("`"),
                pl.col("name"),
                pl.lit("` is a public module constant rather than a private file detail"),
            ),
            (("public module constant", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
    )


def predicate_fix(
    relations: SymbolRelations,
    selected: pl.LazyFrame,
    prefix: str,
) -> FixQuery:
    """Rename repairable predicates at their declaration and every resolved reference."""
    repairable = selected.filter(
        pl.col("reference.id").is_not_null()
        & pl.col("reference.are_references_complete").fill_null(False)
    ).with_columns(
        pl.concat_str(
            pl.col("name").str.extract(r"^(_*)", 1),
            pl.lit(prefix),
            pl.col("name").str.strip_chars_start("_"),
        ).alias("new_name")
    )
    rewrites = repairable.select(
        "fact_id",
        pl.col("ordinal").cast(pl.UInt64).alias("rewrite_order"),
        pl.lit("rename").alias("kind"),
        pl.lit("").alias("source"),
        pl.lit("").alias("placement"),
        pl.col("new_name").alias("name"),
        pl.col("reference.id").alias("symbol_id"),
        pl.col("reference.name").alias("symbol_name"),
        pl.col("reference.are_references_complete").alias("references_complete"),
    )
    declarations = repairable.select(
        "fact_id",
        pl.col("ordinal").cast(pl.UInt64).alias("rewrite_order"),
        pl.lit("declaration").alias("role"),
        pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
        pl.col("reference.declaration.id").alias("id"),
        pl.col("reference.declaration.span.path").alias("path"),
        pl.col("reference.declaration.span.start_line").cast(pl.UInt64).alias("start_line"),
        pl.col("reference.declaration.span.start_column").cast(pl.UInt64).alias("start_column"),
        pl.col("reference.declaration.span.end_line").cast(pl.UInt64).alias("end_line"),
        pl.col("reference.declaration.span.end_column").cast(pl.UInt64).alias("end_column"),
        pl.col("reference.declaration.kind").alias("kind"),
        pl.col("reference.declaration.text").alias("text"),
    )
    references = (
        relations.references()
        .join(
            repairable.select(
                "fact_id",
                pl.col("record_id").alias("parent_id"),
                pl.col("ordinal").cast(pl.UInt64).alias("rewrite_order"),
            ),
            on=["fact_id", "parent_id"],
            how="inner",
        )
        .select(
            "fact_id",
            "rewrite_order",
            pl.lit("reference").alias("role"),
            "ordinal",
            "id",
            "path",
            "start_line",
            "start_column",
            "end_line",
            "end_column",
            "kind",
            "text",
        )
    )
    return FixQuery.build(
        "Rename each predicate at its declaration and at every reference bound to it.",
        rewrites=rewrites,
        nodes=pl.concat([declarations, references], how="vertical"),
    )
