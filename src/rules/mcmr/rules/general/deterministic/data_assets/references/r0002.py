import polars as pl

from ...... import rule
from ......domain.contracts import FixSafety
from ......facts import DataFieldReferenceFact
from ......query import CountQuery, FixQuery, RuleQuery
from ......table import Table
from ..relations import detailed_count_query


@rule("ALL-DATA0002", fix_safety=FixSafety.SAFE)
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

    The repair rewrites the literal that named the retired column so it names the column the
    catalog itself proves replaced it, and it is offered only when the provider retained that
    proof. Column-level lineage naming exactly one surviving successor is the whole evidence, so a
    column with two successors, none, or a name the literal spells more than once is reported
    without a patch. MCMR reparses the rewritten file and reruns this rule before keeping the edit.

    Exceptions
    ----------
    A read of a field that exists is not judged here even when its type disagrees, since that is
    what `ALL-DATA0003` answers. A read whose asset is missing is excluded entirely, so one root
    cause is never counted twice. A field a query selects through a wildcard or builds by
    interpolation names nothing exactly and never reaches this stream, which under-reports and
    never over-reports. One literal receives at most one rewrite in a run, because two edits to the
    same string would overlap, so a query retiring two columns closes over two verified runs.

    Examples
    --------
    Reading `orders.legacy_total` from a schema holding only `orders.total` returns `1`. Reading
    `orders.total` returns `0`, and so does reading `archive.total` when `archive` itself is absent
    from the catalog, because that reference belongs to `ALL-DATA0001`.

    References
    ----------
    Cites "dbt documentation", catalog artifact schema
    Cites "OpenAPI Specification", property compatibility principles
    Cites "DataHub documentation", column-level lineage
    """
    selected = subject.records("references").filter(
        pl.col("asset_exists") & ~pl.col("field_exists")
    )
    repairable = (
        selected.filter(pl.col("repair.replacement") != "")
        .unique("fact_id", keep="first", maintain_order=True)
        .with_columns(pl.lit(0, dtype=pl.UInt64).alias("rewrite_order"))
    )
    query = detailed_count_query(
        subject,
        selected,
        pl.concat_str(
            pl.lit("field `"),
            pl.col("asset_identifier"),
            pl.lit("."),
            pl.col("field_name"),
            pl.lit("` is absent from the catalog schema"),
        ),
        "missing data field reference",
    )
    return RuleQuery[int](
        values=query.values,
        findings=query.findings,
        fix=FixQuery.build(
            "Name the column the catalog proves replaced the retired one.",
            rewrites=repairable.select(
                "fact_id",
                "rewrite_order",
                pl.lit("replace").alias("kind"),
                pl.col("repair.replacement").alias("source"),
                pl.lit("").alias("placement"),
                pl.lit("").alias("name"),
                pl.lit("").alias("symbol_id"),
                pl.lit("").alias("symbol_name"),
                pl.lit(False).alias("references_complete"),
            ),
            nodes=repairable.select(
                "fact_id",
                "rewrite_order",
                pl.lit("target").alias("role"),
                pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
                pl.col("repair.node.id").alias("id"),
                pl.col("repair.node.span.path").alias("path"),
                pl.col("repair.node.span.start_line").cast(pl.UInt64).alias("start_line"),
                pl.col("repair.node.span.start_column").cast(pl.UInt64).alias("start_column"),
                pl.col("repair.node.span.end_line").cast(pl.UInt64).alias("end_line"),
                pl.col("repair.node.span.end_column").cast(pl.UInt64).alias("end_column"),
                pl.col("repair.node.kind").alias("kind"),
                pl.col("repair.node.text").alias("text"),
            ),
        ),
    )
