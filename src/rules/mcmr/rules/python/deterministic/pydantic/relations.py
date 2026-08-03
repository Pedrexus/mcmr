import polars as pl

from .....facts import PydanticModelFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table.relations import FactRelations


class PydanticModelTables(FactRelations[PydanticModelFact]):
    """Expose normalized model analysis relations and provider evidence."""

    def fields(self) -> pl.LazyFrame:
        """Return every field beside its owning model identity and order."""
        models = self.models().select(
            "fact_id",
            pl.col("record_id").alias("model_id"),
            pl.col("ordinal").alias("model_order"),
            pl.col("name").alias("model_name"),
            pl.col("is_pydantic_model").alias("owner_is_pydantic_model"),
        )
        return self.records("models.fields").join(
            models,
            left_on=["fact_id", "parent_id"],
            right_on=["fact_id", "model_id"],
            how="inner",
        )

    def models(self) -> pl.LazyFrame:
        """Return every analyzed model candidate."""
        return self.records("models")

    def validators(self) -> pl.LazyFrame:
        """Return every validator nested under its model candidate."""
        return self.records("models.validators")


def count_query(frame: pl.LazyFrame, measurement: str) -> CountQuery:
    """Return the standard exact count query for a model analysis relation."""
    value = pl.col("value")
    return RuleQuery.integer(
        frame,
        value,
        findings=FindingQuery.precise_integer(
            frame,
            value,
            measurement,
            evidence=pl.col("evidence"),
        ),
    )
