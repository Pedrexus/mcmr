import polars as pl

from ...... import Numeric, rule
from ......facts import DataAssetFact
from ......query import PercentageQuery
from ......table import Table
from ..relations import percentage_query


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
    descriptions = pl.concat(
        [
            subject.records("assets").select("fact_id", "description"),
            subject.records("assets.fields").select("fact_id", "description"),
        ]
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
    return percentage_query(
        frame,
        "data definition gap percentage",
    )
