import polars as pl

from ...... import rule
from ......facts import DataFieldReferenceFact
from ......query import CountQuery
from ......table import Table
from ..relations import detailed_count_query


@rule("ALL-DATA0003")
def incompatible_data_field_type(subject: Table[DataFieldReferenceFact]) -> CountQuery:
    """Count explicit source type expectations that disagree with catalog schemas.

    Definition
    ----------
    Compare the type a source location states it expects against the type the catalog records for
    that field, and report the pairs that disagree. Comparison folds case and trims whitespace, so
    ` DECIMAL ` and `decimal` agree, and nothing else is normalized here. A disagreement is a
    decoding error waiting to happen, and it surfaces as a wrong number rather than as a crash
    whenever the two types are silently coercible.

    Only a stated expectation is judged. Normalizing types that are compatible without being
    spelled alike, such as an integer widening or a timestamp precision, belongs in the provider
    that builds the snapshot, because only it knows the engine whose rules decide compatibility.

    Evidence
    --------
    Each finding records the source location, the field, the type the source expects, and the type
    the catalog records. The value is the number of stated expectations that disagree with the
    catalog.

    Exceptions
    ----------
    A read that states no expectation is not judged, since an empty expectation is a question about
    documentation rather than a disagreement. A field or asset the catalog does not hold is left to
    `ALL-DATA0001` and `ALL-DATA0002`, so a missing column is never also reported as a type
    conflict. Two spellings a provider already normalized arrive equal and are not reported, which
    is how a project teaches this rule about its own engine's coercions.

    Examples
    --------
    A source expecting `integer` where the catalog records `string` returns `1`. A source expecting
    ` DECIMAL ` where the catalog records `decimal` returns `0`, because case and surrounding
    whitespace are folded. A source stating no expectation at all returns `0`.

    References
    ----------
    Cites "Apache Avro specification", schema resolution
    Cites "JSON Schema", type system
    """
    expected = pl.col("expected_type").str.strip_chars().str.to_lowercase()
    catalog = pl.col("catalog_type").str.strip_chars().str.to_lowercase()
    selected = subject.records("references").filter(
        pl.col("asset_exists")
        & pl.col("field_exists")
        & (pl.col("expected_type").str.strip_chars() != "")
        & (expected != catalog)
    )
    return detailed_count_query(
        subject,
        selected,
        pl.concat_str(
            pl.lit("field `"),
            pl.col("asset_identifier"),
            pl.lit("."),
            pl.col("field_name"),
            pl.lit("` expects `"),
            pl.col("expected_type"),
            pl.lit("` but the catalog declares `"),
            pl.col("catalog_type"),
            pl.lit("`"),
        ),
        "incompatible data field type",
    )
