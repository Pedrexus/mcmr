import polars as pl
from pydantic import NonNegativeInt

from ...... import rule
from ......domain.contracts import FixSafety
from ......facts import FunctionFact
from ......query import FindingQuery, FixQuery, RuleQuery
from ......table import FunctionRelation, Table


@rule("ALL-FUNC0004", fix_safety=FixSafety.REVIEW)
def unnecessary_one_line_concrete_function(
    subject: Table[FunctionFact],
    *,
    minimum_references: NonNegativeInt = 2,
) -> RuleQuery[bool]:
    """Find one-line nested functions whose named boundary lacks demonstrated reuse.

    Definition
    ----------
    Inspect nested functions whose complete reference scope is statically visible. Omit an optional
    docstring and count nonblank, non-comment physical lines in the executable body. Report a
    concrete nested function with exactly one implementation line when direct calls remain below
    `minimum_references`, which defaults to two. Public module functions and methods remain public
    boundaries because repository references cannot disprove external callers or dynamic dispatch.

    Evidence
    --------
    Each finding identifies the definition, structural role, one-line measurement, project
    reference count, and every matching reference location. The result value is the number of
    shallow concrete boundaries that lack the configured reuse evidence.

    Exceptions
    ----------
    Properties, abstract methods, Protocol contracts, overloaded APIs and implementations, special
    methods, recursion, `pass` or ellipsis bodies, and `NotImplementedError` placeholders are
    excluded. A nested function passed as a first-class callable is retained because it cannot be
    replaced by its expression. Functions meeting the reuse threshold remain as named boundaries.
    ALL-FUNC0002 exclusively owns private module helpers, while Vulture owns unused private
    functions.

    Examples
    --------
    A nested `normalize` called once and containing only `return value.strip()` is reported even
    when a long docstring precedes the return. The same function used at two call sites is
    accepted. A callback passed to `map`, public API, one-line property, abstract method, or
    overload implementation is accepted regardless of visible repository reuse.

    References
    ----------
    Cites "Refactoring", Inline Function
    https://refactoring.com/catalog/inlineFunction.html
    Cites "A Philosophy of Software Design", chapter 4, deep and shallow modules
    Cites "The Python Language Reference", special method names
    https://docs.python.org/3/reference/datamodel.html#special-method-names
    Cites "Python typing specification", Protocols
    https://typing.python.org/en/latest/spec/protocol.html
    Cites "Python typing specification", overloads
    https://typing.python.org/en/latest/spec/overload.html
    """
    frame = subject.lazy(FunctionRelation.FUNCTIONS)
    exempt = (
        pl.col("is_property")
        | pl.col("is_abstract")
        | pl.col("is_protocol_member")
        | pl.col("is_overload")
        | pl.col("is_protocol_name")
        | pl.col("is_recursive")
        | pl.col("is_first_class_reference")
        | pl.col("is_pass_body")
        | pl.col("is_raise_body")
    )
    value = (
        (pl.col("scope") == "nested")
        & (pl.col("implementation_lines") == 1)
        & (pl.col("reference_count") < minimum_references)
        & ~exempt
    )
    references = subject.lazy(FunctionRelation.REFERENCES)
    repairable = frame.filter(
        pl.col("definition_id").is_not_null() & pl.col("body_expression_id").is_not_null()
    ).join(
        references.select("function_id").unique(),
        left_on="entity_id",
        right_on="function_id",
        how="inner",
    )
    rewrites = repairable.select(
        "fact_id",
        pl.lit(0, dtype=pl.UInt64).alias("rewrite_order"),
        pl.lit("inline").alias("kind"),
        pl.lit("").alias("source"),
        pl.lit("").alias("placement"),
        pl.lit("").alias("name"),
        pl.lit("").alias("symbol_id"),
        pl.lit("").alias("symbol_name"),
        pl.lit(False).alias("references_complete"),
    )
    definition_nodes = repairable.select(
        "fact_id",
        pl.lit(0, dtype=pl.UInt64).alias("rewrite_order"),
        pl.lit("declaration").alias("role"),
        pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
        pl.col("definition_id").alias("id"),
        pl.col("definition_path").alias("path"),
        pl.col("definition_start_line").alias("start_line"),
        pl.col("definition_start_column").alias("start_column"),
        pl.col("definition_end_line").alias("end_line"),
        pl.col("definition_end_column").alias("end_column"),
        pl.col("definition_kind").alias("kind"),
        pl.col("definition_text").alias("text"),
    )
    body_nodes = repairable.select(
        "fact_id",
        pl.lit(0, dtype=pl.UInt64).alias("rewrite_order"),
        pl.lit("body").alias("role"),
        pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
        pl.col("body_expression_id").alias("id"),
        pl.col("body_expression_path").alias("path"),
        pl.col("body_expression_start_line").alias("start_line"),
        pl.col("body_expression_start_column").alias("start_column"),
        pl.col("body_expression_end_line").alias("end_line"),
        pl.col("body_expression_end_column").alias("end_column"),
        pl.col("body_expression_kind").alias("kind"),
        pl.col("body_expression_text").alias("text"),
    )
    reference_nodes = references.join(
        repairable.select("entity_id", "fact_id"),
        left_on="function_id",
        right_on="entity_id",
        how="inner",
    ).select(
        "fact_id",
        pl.lit(0, dtype=pl.UInt64).alias("rewrite_order"),
        pl.lit("reference").alias("role"),
        "ordinal",
        pl.col("node_id").alias("id"),
        "path",
        "start_line",
        "start_column",
        "end_line",
        "end_column",
        "kind",
        "text",
    )
    fix = FixQuery.build(
        "Replace each reference with the one line it stands for, then delete the declaration.",
        rewrites=rewrites,
        nodes=pl.concat(
            [definition_nodes, body_nodes, reference_nodes],
            how="vertical",
        ).sort("fact_id", "rewrite_order", "role", "ordinal"),
    )
    return RuleQuery.boolean(
        frame,
        value,
        findings=FindingQuery.precise_boolean(
            frame, value, "unnecessary one line concrete function"
        ),
        fix=fix,
    )
