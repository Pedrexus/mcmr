import polars as pl

from ..... import rule
from .....domain.contracts import Unit
from .....facts import CallFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table import CallRelation, Table

_DEVICE_DESTINATIONS = {
    "cupy.array",
    "cupy.asarray",
    "cupy.from_dlpack",
    "cudf.DataFrame.from_pandas",
    "cudf.Series.from_pandas",
    "torch.as_tensor",
    "torch.from_numpy",
    "torch.tensor",
    "torch.utils.dlpack.from_dlpack",
}
_HOST_BRIDGES = {
    "cudf.DataFrame.to_pandas",
    "cudf.Series.to_pandas",
    "cupy.asnumpy",
    "cupy.ndarray.get",
    "cupy.ndarray.toDlpack",
    "torch.Tensor.cpu",
    "torch.Tensor.numpy",
    "torch.utils.dlpack.to_dlpack",
}


@rule("PY-PERF0001")
def tensor_interoperability_round_trip_count(subject: Table[CallFact]) -> CountQuery:
    """Find avoidable host, NumPy, or explicit DLPack tensor round trips.

    Definition
    ----------
    Resolve explicit Torch, CuPy, and RAPIDS import aliases. Report a recognized destination call
    only when its argument syntax proves an intermediate `cpu`, `numpy`, `asnumpy`, `to_pandas`, or
    explicit `to_dlpack` conversion from another supported tensor ecosystem. These libraries expose
    direct CUDA array or DLPack interoperability, so application code should pass the device object
    directly when the installed versions support that contract.

    Evidence
    --------
    Each finding identifies the complete destination call and classifies the unnecessary bridge.
    The value is the number of destination calls fed through an avoidable host bridge.

    Exceptions
    ----------
    Unqualified constructors, unknown aliases, serialization, deliberate host ownership, device
    changes, and a plain `from_dlpack(value)` call are excluded. A boundary may keep an explicit
    bridge when version constraints or lifetime semantics require it.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       array = cp.asarray(tensor.cpu().numpy())
       tensor = torch.from_numpy(cp.asnumpy(array))
       array = cp.from_dlpack(torch.utils.dlpack.to_dlpack(tensor))

    Good
    ~~~~
    .. code-block:: python

       array = cp.asarray(tensor)
       tensor = torch.as_tensor(array)

    References
    ----------
    Cites "CuPy documentation", interoperability with PyTorch and the CUDA Array Interface
    https://docs.cupy.dev/en/stable/user_guide/interoperability.html
    Cites "PyTorch documentation", `torch.as_tensor` interoperability
    https://docs.pytorch.org/docs/stable/generated/torch.as_tensor.html
    Cites "cuDF documentation", CuPy interoperability guide
    https://docs.rapids.ai/api/cudf/stable/user_guide/cupy-interop/
    """
    facts = subject.lazy(CallRelation.FACTS)
    evidence = (
        subject.lazy(CallRelation.EVIDENCE)
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("signal").sort_by("ordinal").alias("evidence"))
    )
    mapping_descendants = (
        subject.lazy(CallRelation.EXPRESSION_ANCESTRY)
        .filter(pl.col("relation") == "mapping_value")
        .select("descendant_expression_id")
        .unique()
    )
    bridges = (
        subject.lazy(CallRelation.EXPRESSIONS)
        .filter(
            (pl.col("root_relation") == "argument") & pl.col("qualified_name").is_in(_HOST_BRIDGES)
        )
        .join(
            mapping_descendants,
            left_on="expression_id",
            right_on="descendant_expression_id",
            how="anti",
        )
        .with_columns(
            pl.concat_str(pl.lit("`"), pl.col("qualified_name"), pl.lit("`")).alias("bridge_name")
        )
        .group_by("call_id", maintain_order=True)
        .agg(pl.col("bridge_name").sort_by("preorder").str.join(", ").alias("bridge_names"))
    )
    selected = (
        subject.lazy(CallRelation.CALLS)
        .join(facts.select("fact_id"), on="fact_id", how="inner")
        .filter(pl.col("qualified_name").is_in(_DEVICE_DESTINATIONS) & ~pl.col("is_shadowed"))
        .join(bridges, on="call_id", how="inner")
    )
    counts = selected.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("value")
    )
    frame = facts.join(counts, on="fact_id", how="left").with_columns(pl.col("value").fill_null(0))
    finding_rows = (
        selected.select(
            "fact_id",
            "ordinal",
            "qualified_name",
            "bridge_names",
            pl.col("node_path").alias("path"),
            pl.col("node_start_line").alias("start_line"),
            pl.col("node_start_column").alias("start_column"),
            pl.col("node_end_line").alias("end_line"),
            pl.col("node_end_column").alias("end_column"),
        )
        .join(evidence, on="fact_id", how="left")
        .with_columns(pl.col("evidence").fill_null(pl.lit([], dtype=pl.List(pl.String))))
    )
    value = pl.col("value")
    return RuleQuery.integer(
        frame,
        value,
        findings=FindingQuery.build(
            finding_rows,
            pl.concat_str(
                pl.lit("`"),
                pl.col("qualified_name"),
                pl.lit("` receives a value routed through "),
                pl.col("bridge_names"),
            ),
            (("tensor interoperability round trip count", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
    )
