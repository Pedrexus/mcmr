from typing import TYPE_CHECKING

import polars as pl

from .....domain.contracts import Unit
from .....facts import ProseSegmentFact
from .....query import FindingQuery, PercentageQuery, RuleQuery
from .....table.relations import FactRelations

if TYPE_CHECKING:
    from collections.abc import Sequence


class ProseRelations(FactRelations[ProseSegmentFact]):
    """Derive prose rhythm measures from normalized section relations."""

    def lengths(self, relation: str) -> pl.LazyFrame:
        """Return measured word counts under one section distribution."""
        return self.values(relation).select(
            "fact_order",
            "fact_id",
            pl.col("parent_id").alias("section_id"),
            "ordinal",
            pl.col("integer_value").cast(pl.Float64).alias("length"),
        )

    def opener_concentrations(
        self,
        minimum_sentences: int,
        ignored_openers: Sequence[str],
    ) -> pl.LazyFrame:
        """Return each eligible section's dominant opener and its share."""
        ignored = [word.casefold() for word in ignored_openers]
        openers = self.values("sections.sentence_openers").select(
            "fact_id",
            pl.col("parent_id").alias("section_id"),
            pl.col("string_value").str.to_lowercase().alias("opener"),
        )
        if ignored:
            openers = openers.filter(~pl.col("opener").is_in(ignored))
        counts = openers.group_by("fact_id", "section_id", "opener", maintain_order=True).agg(
            pl.len().cast(pl.UInt64).alias("opener_count")
        )
        totals = counts.group_by("fact_id", "section_id", maintain_order=True).agg(
            pl.col("opener_count").sum().alias("sentence_count")
        )
        eligible = (
            counts.join(totals, on=["fact_id", "section_id"], how="inner")
            .filter(pl.col("sentence_count") >= minimum_sentences)
            .sort(
                "fact_id",
                "section_id",
                "opener_count",
                "opener",
                descending=[False, False, True, False],
            )
            .group_by("fact_id", "section_id", maintain_order=True)
            .agg(
                pl.col("opener").first(),
                pl.col("opener_count").first(),
                pl.col("sentence_count").first(),
            )
            .with_columns(
                (pl.col("opener_count") / pl.col("sentence_count") * 100.0).alias("share")
            )
        )
        return self.sections().join(
            eligible,
            left_on=["fact_id", "record_id"],
            right_on=["fact_id", "section_id"],
            how="inner",
        )

    def sections(self) -> pl.LazyFrame:
        """Return prose sections located at their owning document."""
        sections = self.records("sections").select(
            "fact_order",
            "fact_id",
            "record_id",
            "ordinal",
        )
        return sections.join(
            self.facts(),
            on=["fact_order", "fact_id"],
            how="inner",
        )

    def uniformity(
        self,
        relation: str,
        *,
        minimum_entries: int,
        minimum_words: int,
    ) -> pl.LazyFrame:
        """Return the greatest eligible inverse normalized deviation per document."""
        lengths = self.lengths(relation).filter(pl.col("length") >= minimum_words)
        means = lengths.group_by("fact_id", "section_id", maintain_order=True).agg(
            pl.len().cast(pl.UInt64).alias("entry_count"),
            pl.col("length").mean().alias("mean"),
        )
        eligible = means.filter(pl.col("entry_count") >= minimum_entries)
        sections = (
            lengths.join(eligible, on=["fact_id", "section_id"], how="inner")
            .group_by("fact_id", "section_id", maintain_order=True)
            .agg(
                pl.col("entry_count").first(),
                pl.col("mean").first(),
                (pl.col("length") - pl.col("mean")).abs().mean().alias("deviation"),
            )
            .with_columns(
                (
                    pl.max_horizontal(
                        pl.lit(0.0),
                        1.0 - pl.col("deviation") / pl.col("mean"),
                    )
                    * 100.0
                ).alias("uniformity")
            )
        )
        greatest = sections.group_by("fact_id", maintain_order=True).agg(
            pl.col("uniformity").max().alias("value")
        )
        return (
            self.facts()
            .join(greatest, on="fact_id", how="left")
            .with_columns(pl.col("value").fill_null(0.0))
        )


def percentage_query(frame: pl.LazyFrame, measurement: str) -> PercentageQuery:
    """Return one precise percentage finding per document."""
    value = pl.col("value")
    findings = FindingQuery.build(
        frame,
        pl.concat_str(
            pl.lit(f"{measurement} is "),
            value.round_sig_figs(4).cast(pl.String).str.replace(r"\.0$", ""),
            pl.lit(" percent for `"),
            pl.col("fact_id"),
            pl.lit("`"),
        ),
        ((measurement, value, Unit.PERCENTAGE),),
        evidence=pl.col("evidence"),
    )
    return RuleQuery.floating(frame, value, findings=findings)
