import polars as pl
from pydantic import NonNegativeInt

from ..... import rule
from .....domain.contracts import (
    FixSafety,
    Unit,
)
from .....facts import CallFact
from .....query import CountQuery, FindingQuery, FixQuery, RuleQuery
from .....table import CallRelation, Table

_TENSOR_METHODS = {
    "torch.abs": "abs",
    "torch.acos": "acos",
    "torch.asin": "asin",
    "torch.atan": "atan",
    "torch.ceil": "ceil",
    "torch.cos": "cos",
    "torch.cosh": "cosh",
    "torch.erf": "erf",
    "torch.erfinv": "erfinv",
    "torch.exp": "exp",
    "torch.exp2": "exp2",
    "torch.expm1": "expm1",
    "torch.floor": "floor",
    "torch.frac": "frac",
    "torch.log": "log",
    "torch.log10": "log10",
    "torch.log1p": "log1p",
    "torch.log2": "log2",
    "torch.neg": "neg",
    "torch.reciprocal": "reciprocal",
    "torch.relu": "relu",
    "torch.round": "round",
    "torch.rsqrt": "rsqrt",
    "torch.sigmoid": "sigmoid",
    "torch.sign": "sign",
    "torch.sin": "sin",
    "torch.sinh": "sinh",
    "torch.sqrt": "sqrt",
    "torch.square": "square",
    "torch.tan": "tan",
    "torch.tanh": "tanh",
    "torch.trunc": "trunc",
}
_POWER_FUNCTIONS = {"torch.pow", "torch.float_power"}


def _valid_paths(
    subject: Table[CallFact],
) -> tuple[pl.LazyFrame, pl.LazyFrame, pl.LazyFrame]:
    """Return facts, evidence, and fully matched tensor-operation paths."""
    facts = subject.lazy(CallRelation.FACTS)
    evidence = (
        subject.lazy(CallRelation.EVIDENCE)
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("signal").sort_by("ordinal").alias("evidence"))
    )
    expressions = subject.lazy(CallRelation.EXPRESSIONS)
    ancestry = subject.lazy(CallRelation.EXPRESSION_ANCESTRY)
    edges = ancestry.select(
        "parent_id",
        "parent_kind",
        "child_expression_id",
        "relation",
        "ordinal",
    ).unique(maintain_order=True)
    arguments = (
        edges.filter(pl.col("relation") == "argument")
        .join(
            expressions.select(
                pl.col("expression_id").alias("child_expression_id"),
                pl.col("text").alias("child_text"),
                pl.col("literal_kind").alias("child_literal_kind"),
            ),
            on="child_expression_id",
            how="inner",
        )
        .group_by("parent_id", "parent_kind", maintain_order=True)
        .agg(
            pl.len().cast(pl.UInt64).alias("argument_count"),
            pl.col("child_text")
            .filter(pl.col("ordinal") == 0)
            .first()
            .alias("first_argument_text"),
            pl.col("child_literal_kind")
            .filter(pl.col("ordinal") == 0)
            .first()
            .alias("first_argument_literal_kind"),
        )
    )
    keyword_calls = subject.lazy(CallRelation.KEYWORDS).select("call_id").unique()
    call_parents = (
        subject.lazy(CallRelation.CALLS)
        .join(keyword_calls, on="call_id", how="anti")
        .filter(~pl.col("is_shadowed"))
        .select(
            pl.col("call_id").alias("parent_id"),
            pl.lit("call").alias("parent_kind"),
            "qualified_name",
        )
    )
    expression_parents = expressions.select(
        pl.col("expression_id").alias("parent_id"),
        pl.lit("expression").alias("parent_kind"),
        "qualified_name",
    )
    parents = pl.concat([call_parents, expression_parents], how="vertical").join(
        arguments, on=["parent_id", "parent_kind"], how="inner"
    )
    ordinary_method = pl.col("qualified_name").replace_strict(_TENSOR_METHODS, default="")
    ordinary = (ordinary_method != "") & (pl.col("argument_count") == 1)
    power = (
        pl.col("qualified_name").is_in(_POWER_FUNCTIONS)
        & (pl.col("argument_count") == 2)
        & (pl.col("first_argument_literal_kind") == "number")
        & pl.col("first_argument_text").is_in(["2", "2.0"])
    )
    operations = parents.filter(ordinary | power).select(
        "parent_id",
        "parent_kind",
        pl.when(power)
        .then(pl.lit(1, dtype=pl.UInt64))
        .otherwise(pl.lit(0, dtype=pl.UInt64))
        .alias("operand_ordinal"),
        pl.when(power).then(pl.lit("exp2")).otherwise(ordinary_method).alias("method"),
    )
    eligible_edges = edges.filter(pl.col("relation") == "argument").join(
        operations,
        left_on=["parent_id", "parent_kind", "ordinal"],
        right_on=["parent_id", "parent_kind", "operand_ordinal"],
        how="inner",
    )
    path_lengths = ancestry.group_by(
        "call_id", "descendant_expression_id", maintain_order=True
    ).agg(pl.len().cast(pl.UInt64).alias("operation_count"))
    matched = ancestry.join(
        eligible_edges.select("parent_id", "parent_kind", "child_expression_id", "method"),
        on=["parent_id", "parent_kind", "child_expression_id"],
        how="inner",
    )
    valid_paths = (
        matched.group_by("call_id", "descendant_expression_id", maintain_order=True)
        .agg(
            pl.len().cast(pl.UInt64).alias("matched_count"),
            pl.concat_str(pl.lit("`"), pl.col("method"), pl.lit("`"))
            .sort_by("step", descending=True)
            .str.join(", ")
            .alias("method_names"),
            pl.concat_str(pl.lit("."), pl.col("method"), pl.lit("()"))
            .sort_by("step", descending=True)
            .str.join("")
            .alias("ordinary_chain"),
            pl.concat_str(pl.lit("."), pl.col("method"), pl.lit("_()"))
            .sort_by("step", descending=True)
            .str.join("")
            .alias("in_place_chain"),
        )
        .join(path_lengths, on=["call_id", "descendant_expression_id"], how="inner")
        .filter(pl.col("matched_count") == pl.col("operation_count"))
        .sort(["call_id", "operation_count"], descending=[False, True])
        .unique(subset=["call_id"], keep="first", maintain_order=True)
        .join(
            expressions.select(
                pl.col("expression_id").alias("descendant_expression_id"),
                pl.col("text").alias("tensor_text"),
            ),
            on="descendant_expression_id",
            how="inner",
        )
    )
    return facts, evidence, valid_paths


def _selected_calls(
    subject: Table[CallFact],
    *,
    facts: pl.LazyFrame,
    valid_paths: pl.LazyFrame,
    minimum_operations: int,
) -> pl.LazyFrame:
    """Keep the outermost qualifying fluent candidate for each nested call chain."""
    candidates = (
        subject.lazy(CallRelation.CALLS)
        .join(facts.select("fact_id"), on="fact_id", how="inner")
        .join(valid_paths, on="call_id", how="inner")
        .filter(pl.col("operation_count") >= minimum_operations)
        .with_row_index("candidate_id")
    )
    contained = (
        candidates.join(candidates, on="fact_id", how="inner", suffix="_outer")
        .filter(
            (pl.col("candidate_id") != pl.col("candidate_id_outer"))
            & (pl.col("operation_count_outer") > pl.col("operation_count"))
            & (
                (pl.col("node_start_line_outer") < pl.col("node_start_line"))
                | (
                    (pl.col("node_start_line_outer") == pl.col("node_start_line"))
                    & (pl.col("node_start_column_outer") <= pl.col("node_start_column"))
                )
            )
            & (
                (pl.col("node_end_line_outer") > pl.col("node_end_line"))
                | (
                    (pl.col("node_end_line_outer") == pl.col("node_end_line"))
                    & (pl.col("node_end_column_outer") >= pl.col("node_end_column"))
                )
            )
        )
        .select("candidate_id")
        .unique()
    )
    return candidates.join(contained, on="candidate_id", how="anti")


def _repair_frames(selected: pl.LazyFrame) -> tuple[pl.LazyFrame, pl.LazyFrame]:
    """Build the replacement text and exact source node for every selected chain."""
    rewrites = selected.select(
        "fact_id",
        pl.col("ordinal").alias("rewrite_order"),
        pl.lit("replace").alias("kind"),
        pl.concat_str(
            pl.col("tensor_text"),
            pl.when(
                (pl.col("assigned_target") != "")
                & (pl.col("assigned_target") == pl.col("tensor_text"))
            )
            .then(pl.col("in_place_chain"))
            .otherwise(pl.col("ordinary_chain")),
        ).alias("source"),
        pl.lit("").alias("placement"),
        pl.lit("").alias("name"),
        pl.lit("").alias("symbol_id"),
        pl.lit("").alias("symbol_name"),
        pl.lit(False).alias("references_complete"),
    )
    nodes = selected.select(
        "fact_id",
        pl.col("ordinal").alias("rewrite_order"),
        pl.lit("target").alias("role"),
        pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
        pl.col("node_id").alias("id"),
        pl.col("node_path").alias("path"),
        pl.col("node_start_line").alias("start_line"),
        pl.col("node_start_column").alias("start_column"),
        pl.col("node_end_line").alias("end_line"),
        pl.col("node_end_column").alias("end_column"),
        pl.col("node_kind").alias("kind"),
        pl.col("node_text").alias("text"),
    )
    return rewrites, nodes


@rule("PY-TORC0001", fix_safety=FixSafety.SAFE)
def fluent_tensor_call_chain(
    subject: Table[CallFact], *, minimum_operations: NonNegativeInt = 2
) -> CountQuery:
    """Count nested Torch function calls that a fluent tensor chain states more directly.

    Definition
    ----------
    Resolve unshadowed Torch functions whose behavior a tensor already exposes as a method, then
    fold each nested application over one tensor into the chain it is equivalent to. Report a call
    whose chain reaches `minimum_operations` operations, because that is the point where the nested
    form reverses reading order and hides the tensor the operations act on. A power over a literal
    base folds into the base method that names it, so `torch.pow(2.0, value)` joins the chain as
    `exp2`. The value is the number of nested calls found.

    Reading order is the whole argument. A fluent chain names the tensor once and then reads left
    to right in the order the operations run, while the nested form names the tensor last and reads
    inside out.

    Evidence
    --------
    Each finding records the outer call range, the resolved tensor, and the ordered methods the
    chain folds into. The rewrite chooses the in-place method of each operation only when the whole
    expression is rebound to the tensor it reads, since that assignment already discards the prior
    value and no other alias can observe the difference.

    Exceptions
    ----------
    A shadowed Torch alias, a keyword argument, an operation with no method form, and a chain
    shorter than `minimum_operations` are all left alone. A single call such as `torch.log2(value)`
    stays valid because there is no reading order to reverse. The rule does not claim that in-place
    operations are generally faster, only that a rebound value cannot observe them.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       sigma = torch.pow(2.0, torch.round(torch.log2(sigma)))
       scaled = torch.sqrt(torch.abs(weights))

    Good
    ~~~~
    .. code-block:: python

       sigma = sigma.log2_().round_().exp2_()
       scaled = weights.abs().sqrt()

    References
    ----------
    Cites "PyTorch documentation", Tensor method reference, including the in-place variants
    https://docs.pytorch.org/docs/stable/tensors.html
    Cites "PyTorch documentation", autograd notes on in-place operations
    https://docs.pytorch.org/docs/stable/notes/autograd.html#in-place-operations-with-autograd
    Cites "PyTorch documentation", `torch.pow`
    https://docs.pytorch.org/docs/stable/generated/torch.pow.html
    """
    facts, evidence, valid_paths = _valid_paths(subject)
    selected = _selected_calls(
        subject,
        facts=facts,
        valid_paths=valid_paths,
        minimum_operations=minimum_operations,
    )
    counts = selected.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("value")
    )
    frame = facts.join(counts, on="fact_id", how="left").with_columns(pl.col("value").fill_null(0))
    finding_rows = (
        selected.select(
            "fact_id",
            "ordinal",
            "node_text",
            "qualified_name",
            "tensor_text",
            "method_names",
            pl.col("node_path").alias("path"),
            pl.col("node_start_line").alias("start_line"),
            pl.col("node_start_column").alias("start_column"),
            pl.col("node_end_line").alias("end_line"),
            pl.col("node_end_column").alias("end_column"),
        )
        .join(evidence, on="fact_id", how="left")
        .with_columns(pl.col("evidence").fill_null(pl.lit([], dtype=pl.List(pl.String))))
    )
    rewrites, nodes = _repair_frames(selected)
    value = pl.col("value")
    return RuleQuery.integer(
        frame,
        value,
        findings=FindingQuery.build(
            finding_rows,
            pl.concat_str(
                pl.lit("`"),
                pl.when(pl.col("node_text") != "")
                .then(pl.col("node_text"))
                .otherwise(pl.col("qualified_name")),
                pl.lit("` reverses the fluent chain on `"),
                pl.col("tensor_text"),
                pl.lit("` through "),
                pl.col("method_names"),
            ),
            (("fluent tensor call chain", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
        fix=FixQuery.build(
            "State each nested chain as the fluent tensor chain it is equivalent to.",
            rewrites=rewrites,
            nodes=nodes,
        ),
    )
