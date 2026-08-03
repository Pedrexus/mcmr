import polars as pl
from patos import FrozenModel, Runtime


class CandidateRelations(FrozenModel):
    """Build the stable contextual payload directly from one family's native relations."""

    facts: Runtime[pl.LazyFrame]
    records: Runtime[pl.LazyFrame]
    values: Runtime[pl.LazyFrame]

    @staticmethod
    def lengths(frame: pl.LazyFrame, *, key: str, name: str) -> pl.LazyFrame:
        """Count one normalized child relation without collecting it."""
        return frame.group_by(key).len(name=name)

    @staticmethod
    def span_columns(*, source: str, target: str) -> tuple[pl.Expr, ...]:
        """Project one flattened source span into its generic dotted field names."""
        return (
            pl.col(f"{source}end_column").cast(pl.Int64).alias(f"{target}.end_column"),
            pl.col(f"{source}end_line").cast(pl.Int64).alias(f"{target}.end_line"),
            pl.col(f"{source}path").alias(f"{target}.path"),
            pl.col(f"{source}start_column").cast(pl.Int64).alias(f"{target}.start_column"),
            pl.col(f"{source}start_line").cast(pl.Int64).alias(f"{target}.start_line"),
        )

    @staticmethod
    def value_rows(source: pl.LazyFrame, relation: str) -> pl.LazyFrame:
        """Project one specialized string child relation into universal value rows."""
        container = pl.concat_str("parent_id", pl.lit(f"/{relation}"))
        container_length = (
            pl.col("container_length")
            if "container_length" in source.collect_schema().names()
            else pl.len().over("parent_id")
        )
        return source.select(
            "fact_order",
            "fact_id",
            pl.lit(relation).alias("relation"),
            "parent_id",
            container.alias("container_id"),
            pl.lit(None, dtype=pl.UInt64).alias("container_ordinal"),
            container_length.cast(pl.UInt64).alias("container_length"),
            pl.lit("value").alias("entry_kind"),
            pl.concat_str(container, pl.lit(":"), pl.col("ordinal")).alias("value_id"),
            pl.col("ordinal").cast(pl.UInt64),
            pl.lit(None, dtype=pl.String).alias("map_key"),
            pl.col("value").alias("string_value"),
            pl.lit(None, dtype=pl.Int64).alias("integer_value"),
            pl.lit(None, dtype=pl.Float64).alias("float_value"),
            pl.lit(None, dtype=pl.Boolean).alias("boolean_value"),
            pl.col("candidate_order_0").cast(pl.Int64),
            pl.col("candidate_order_1").cast(pl.Int64),
            pl.col("candidate_order_2").cast(pl.Int64),
            pl.col("candidate_order_3").cast(pl.Int64),
        )

    def candidates(self) -> pl.LazyFrame:
        """Encode the existing fields, records, values, and evidence payload shape."""
        identity = {
            "fact_order",
            "fact_id",
            "path",
            "start_line",
            "start_column",
            "end_line",
            "end_column",
            "language",
        }
        fact_fields = [
            name for name in self.facts.collect_schema().names() if name not in identity
        ]
        record_fields = [
            name
            for name in self.records.collect_schema().names()
            if name not in {"fact_order", "fact_id"} and not name.startswith("candidate_order")
        ]
        value_fields = [
            name
            for name in self.values.collect_schema().names()
            if name not in {"fact_order", "fact_id"} and not name.startswith("candidate_order")
        ]
        record_order = [
            name
            for name in self.records.collect_schema().names()
            if name.startswith("candidate_order")
        ]
        value_order = [
            name
            for name in self.values.collect_schema().names()
            if name.startswith("candidate_order")
        ]
        record_groups = (
            self.records.sort("fact_order", "ordinal", *record_order)
            .group_by("fact_id", maintain_order=True)
            .agg(pl.struct(*record_fields).alias("records"))
        )
        value_groups = (
            self.values.sort("fact_order", "ordinal", *value_order)
            .group_by("fact_id", maintain_order=True)
            .agg(pl.struct(*value_fields).alias("values"))
        )
        evidence = (
            self.records.filter(
                (pl.col("relation") == "evidence") & pl.col("signal").is_not_null()
            )
            .sort("fact_order", "ordinal")
            .group_by("fact_id", maintain_order=True)
            .agg(pl.struct("signal", "detail", "source", "confidence").alias("evidence"))
        )
        return (
            self.facts.with_columns(pl.struct(*fact_fields).alias("fields"))
            .join(record_groups, on="fact_id", how="left")
            .join(value_groups, on="fact_id", how="left")
            .join(evidence, on="fact_id", how="left")
            .with_columns(
                pl.struct("fields", "records", "values").struct.json_encode().alias("subject_json")
            )
            .select(
                "fact_order",
                "fact_id",
                "path",
                "start_line",
                "start_column",
                "end_line",
                "end_column",
                "language",
                *fact_fields,
                "subject_json",
                "evidence",
            )
        )
