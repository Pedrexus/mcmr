import polars as pl

from ...... import rule
from ......facts import DataFieldReferenceFact
from ......query import CountQuery
from ......table import Table
from ..relations import count_query


@rule("ALL-DATA0002")
def missing_data_field_reference(subject: Table[DataFieldReferenceFact]) -> CountQuery:
    """Count referenced fields absent from an existing data asset schema.

    Definition
    ----------
    Resolve every field one source location reads against the schema the catalog holds for the
    asset that field belongs to, and report a field the schema does not declare. This is the defect
    a type checker cannot see, because the schema lives in the warehouse and the reference is a
    string, so the first evidence of a renamed column is usually a job that failed overnight.

    An asset the catalog does not hold at all is excluded and left to `ALL-DATA0001`, so one
    renamed table produces one finding rather than one for every column somebody read from it.

    Evidence
    --------
    Each finding records the source location, the asset identifier, and the field name the schema
    does not declare. The value is the number of reads naming a field that does not exist.

    Exceptions
    ----------
    A read of a field that exists is not judged here even when its type disagrees, since that is
    what `ALL-DATA0003` answers. A read whose asset is missing is excluded entirely, so one root
    cause is never counted twice. A field a query selects through a wildcard or builds by
    interpolation names nothing exactly and never reaches this stream, which under-reports and
    never over-reports.

    Examples
    --------
    Reading `orders.legacy_total` from a schema holding only `orders.total` returns `1`. Reading
    `orders.total` returns `0`, and so does reading `archive.total` when `archive` itself is absent
    from the catalog, because that reference belongs to `ALL-DATA0001`.

    References
    ----------
    Cites "dbt documentation", catalog artifact schema
    Cites "OpenAPI Specification", property compatibility principles
    """
    selected = subject.records("references").filter(
        pl.col("asset_exists") & ~pl.col("field_exists")
    )
    return count_query(
        subject.counted(selected),
        "missing data field reference",
    )
