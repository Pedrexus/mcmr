import polars as pl

from ...... import Numeric, rule
from ......domain.contracts import Unit
from ......facts import DataAssetFact
from ......query import FindingQuery, PercentageQuery, RuleQuery
from ......table import Table


@rule("ALL-DATA0009", policy=Numeric(maximum=5))
def data_definition_gap_percentage(subject: Table[DataAssetFact]) -> PercentageQuery:
    """Measure cataloged assets and fields lacking a business description.

    Definition
    ----------
    Treat every asset and every field as one object that ought to carry a description, then divide
    the objects whose description is empty once trimmed by the number of objects. A catalog without
    descriptions is a list of names, and the cost lands on whoever has to guess whether `amount` is
    gross or net, in what currency, and as of when.

    Presence is all this measures. Whether a description is accurate or useful is a judgment a
    contextual rule makes, and conflating the two would let a catalog full of restated column names
    score as documented.

    Evidence
    --------
    Each finding names one asset or field whose description is empty. The value is the percentage
    of catalog objects carrying no description, and nothing is inferred from a name that looks
    self-explanatory.

    Exceptions
    ----------
    A description of only whitespace reads as absent, since a field holding a space documents
    nothing. An empty snapshot measures zero rather than one hundred, because there is no
    undocumented object in it to count. A field whose meaning its name genuinely carries still
    counts as undocumented, and a project that disagrees is disagreeing with the rule rather than
    finding an exception to it.

    Examples
    --------
    One asset with an empty description holding two fields, one described and one not, has three
    objects and two gaps, so the value is about `66.7`. An asset described together with its one
    described field returns `0`. An empty snapshot returns `0`.

    References
    ----------
    Cites "DAMA-DMBOK", metadata management principles
    Cites "DataHub documentation", glossary and description metadata
    """
    assets = subject.records("assets")
    fields = subject.records("assets.fields").join(
        assets.select(
            "fact_id",
            pl.col("record_id").alias("asset_record_id"),
            pl.col("identifier").alias("asset_identifier"),
        ),
        left_on=["fact_id", "parent_id"],
        right_on=["fact_id", "asset_record_id"],
        how="left",
    )
    descriptions = pl.concat(
        [assets.select("fact_id", "description"), fields.select("fact_id", "description")]
    )
    summary = descriptions.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("description_count"),
        (pl.col("description").str.strip_chars() == "").sum().cast(pl.UInt64).alias("gap_count"),
    )
    frame = (
        subject.facts()
        .join(summary, on="fact_id", how="left")
        .with_columns(pl.col("description_count", "gap_count").fill_null(0))
        .with_columns(
            pl.when(pl.col("description_count") == 0)
            .then(0.0)
            .otherwise(pl.col("gap_count") / pl.col("description_count") * 100.0)
            .alias("value")
        )
    )
    asset_gaps = assets.filter(pl.col("description").str.strip_chars() == "").select(
        "fact_id",
        pl.col("identifier").alias("object_identifier"),
        pl.lit("asset").alias("object_kind"),
    )
    field_gaps = fields.filter(pl.col("description").str.strip_chars() == "").select(
        "fact_id",
        pl.concat_str(
            pl.col("asset_identifier"),
            pl.lit("."),
            pl.col("name"),
        ).alias("object_identifier"),
        pl.lit("field").alias("object_kind"),
    )
    details = (
        pl.concat([asset_gaps, field_gaps])
        .with_row_index("finding_order")
        .join(subject.facts(), on="fact_id", how="left")
    )
    findings = FindingQuery.build(
        details,
        pl.concat_str(
            pl.col("object_kind"),
            pl.lit(" `"),
            pl.col("object_identifier"),
            pl.lit("` has no description"),
        ),
        (("missing description", pl.lit(1), Unit.COUNT),),
        finding_order=pl.col("finding_order"),
        evidence=pl.col("evidence"),
    )
    return RuleQuery.floating(
        frame,
        pl.col("value"),
        finding_count=pl.col("gap_count"),
        findings=findings,
    )
