from collections.abc import Sequence

import polars as pl

from ...... import rule
from ......facts import DataAssetFact
from ......query import CountQuery
from ......table import Table
from ..relations import detailed_count_query


@rule("ALL-DATA0012")
def ungoverned_sensitive_field(
    subject: Table[DataAssetFact],
    *,
    sensitive_tags: Sequence[str] = ("pii", "sensitive", "confidential", "personal"),
) -> CountQuery:
    """Count fields the catalog marks sensitive while leaving their governance incomplete.

    Definition
    ----------
    Read the tags the catalog attaches to every field, keep the fields carrying one of
    `sensitive_tags`, and report each of them whose asset names no owner or whose own glossary
    terms are empty. A tag says the column holds personal or restricted data, a glossary term says
    which written policy governs it, and an owner says who answers when somebody asks to export it.
    A tag standing alone is a label nobody can act on, which is the state an access review finds
    the week after the data left.

    Tag matching folds case and trims whitespace, since a catalog populated by several teams
    spells the same label as `PII`, `pii`, and a padded variant of both, and treating those as
    three different labels would silently exempt two of them.

    Evidence
    --------
    Each finding names the asset, the field, the tag that made it sensitive, and which of ownership
    and glossary context it lacks. The value is the number of sensitive fields with an incomplete
    governance record.

    Exceptions
    ----------
    A field carrying no tag at all is never reported, because this rule judges what the catalog
    declares sensitive rather than guessing sensitivity from a column name. A sensitive field whose
    asset names an owner and whose glossary terms are stated is complete and stays quiet. A field
    tagged with something outside `sensitive_tags` is left alone, so a project models its own
    vocabulary by stating it rather than by arguing with this list. Whether the named policy is the
    correct one is a judgment nobody makes from metadata alone, so presence is all this measures.

    Examples
    --------
    An `email` field tagged `pii` on an asset with no owner and no glossary term returns `1`. The
    same field on an owned asset carrying one glossary term returns `0`, and so does an untagged
    field on that same unowned asset.

    References
    ----------
    Cites "DAMA-DMBOK", data security and privacy management
    Cites "DataHub documentation", tags and glossary term metadata
    """
    normalized = [tag.strip().casefold() for tag in sensitive_tags]
    sensitive = (
        subject.values("assets.fields.tags")
        .filter(pl.col("string_value").str.strip_chars().str.to_lowercase().is_in(normalized))
        .group_by("fact_id", "parent_id", maintain_order=True)
        .agg(pl.col("string_value").sort_by("ordinal").first().alias("sensitive_tag"))
    )
    owners = subject.records("assets").select(
        "fact_id",
        pl.col("record_id").alias("asset_record_id"),
        pl.col("identifier").alias("asset_identifier"),
        (pl.col("owners.length") == 0).alias("missing_owner"),
    )
    missing_owner = pl.col("missing_owner")
    missing_glossary = pl.col("glossary_terms.length") == 0
    selected = (
        subject.records("assets.fields")
        .join(sensitive, left_on=["fact_id", "record_id"], right_on=["fact_id", "parent_id"])
        .join(
            owners,
            left_on=["fact_id", "parent_id"],
            right_on=["fact_id", "asset_record_id"],
            how="left",
        )
        .filter(missing_owner | missing_glossary)
    )
    return detailed_count_query(
        subject,
        selected,
        pl.concat_str(
            pl.lit("field `"),
            pl.col("asset_identifier"),
            pl.lit("."),
            pl.col("name"),
            pl.lit("` tagged `"),
            pl.col("sensitive_tag"),
            pl.lit("` has "),
            pl.when(missing_owner & missing_glossary)
            .then(pl.lit("no owner and no glossary term"))
            .when(missing_owner)
            .then(pl.lit("no owner"))
            .otherwise(pl.lit("no glossary term")),
        ),
        "ungoverned sensitive field",
    )
