import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import FunctionFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import FunctionRelation, Table


@rule("ALL-PARA0001")
def swappable_parameter_pair(subject: Table[FunctionFact]) -> CountQuery:
    """Count adjacent parameter pairs a caller can silently swap.

    Definition
    ----------
    Compare each pair of adjacent declared parameters and report a pair whose declared types are
    identical and non-empty. Identical adjacent types make a transposed call compile, type-check,
    and run, so nothing but a test can catch it. The count excludes the receiver, which a caller
    never passes explicitly.

    The type compared is the one a caller sees, which in a language writing half of its types in
    the declarator means the pointer, the reference, and the qualifiers that reach the value, not
    the word the declaration happens to name. `int32_t *tokens` and `int32_t start` share no type
    and no caller could transpose them, and neither could one swap `const int32_t *` with
    `int32_t *`, since that conversion runs one way only.

    Evidence
    --------
    Each finding records the callable range, both parameter names, the type they share, and
    where in the parameter list the pair sits. The repair is a choice between separating the two
    types and closing the position off, because only the author knows which one the caller wants.
    The value is the number of swappable adjacent pairs.

    Exceptions
    ----------
    A keyword-only parameter cannot be transposed, because its name travels with its value, so it
    is excluded. A qualifier a caller cannot observe does not separate two types, so `const int`
    beside `int` and `int *const` beside `int *` are each one pair rather than none. Parameters
    whose names make the order self-evident at the call site, such as `width` and `height`, still
    count because the risk lives in the call, not the declaration. The usual repairs are a distinct
    type for each role or a keyword-only contract, which is why a language with mandatory named
    arguments reports none.

    Examples
    --------
    `def copy(source: Path, destination: Path)` returns `1`. `def copy(source: Source, into: Sink)`
    returns `0`, and so does `def resize(*, width: int, height: int)` in a language that can force
    the names. `void merge(int32_t *left, int32_t *right)` returns `1` where
    `void merge(int32_t *left, int32_t count)` returns `0`.

    References
    ----------
    Generalizes clang-tidy bugprone-easily-swappable-parameters
    https://clang.llvm.org/extra/clang-tidy/checks/bugprone/easily-swappable-parameters.html
    Cites "Effective Java", item on parameter lists
    Cites "Refactoring", introduce parameter object
    """
    declared = (
        subject.lazy(FunctionRelation.PARAMETERS)
        .filter(~pl.col("is_receiver") & ~pl.col("is_keyword_only"))
        .sort("function_id", "ordinal")
        .with_columns(
            pl.int_range(1, pl.len() + 1).over("function_id").alias("position"),
            pl.len().over("function_id").cast(pl.UInt64).alias("declared_count"),
        )
    )
    pairs = (
        declared.with_columns(
            pl.col("name").shift(-1).over("function_id").alias("right_name"),
            pl.col("type_name").shift(-1).over("function_id").alias("right_type"),
        )
        .filter((pl.col("type_name") != "") & (pl.col("type_name") == pl.col("right_type")))
        .rename({"name": "left_name"})
    )
    counts = pairs.group_by("function_id").agg(pl.len().cast(pl.UInt64).alias("value"))
    frame = (
        subject.lazy(FunctionRelation.FUNCTIONS)
        .join(counts, left_on="entity_id", right_on="function_id", how="left")
        .with_columns(pl.col("value").fill_null(0))
    )
    finding_rows = pairs.join(
        subject.lazy(FunctionRelation.FUNCTIONS),
        left_on="function_id",
        right_on="entity_id",
        how="inner",
    )
    findings = FindingQuery.build(
        finding_rows,
        pl.concat_str(
            pl.lit("`"),
            pl.col("name"),
            pl.lit("` takes `"),
            pl.col("left_name"),
            pl.lit("` and `"),
            pl.col("right_name"),
            pl.lit("` next to each other and both are `"),
            pl.col("type_name"),
            pl.lit("`, so a caller can transpose them silently"),
        ),
        (
            ("position in the parameter list", pl.col("position"), Unit.COUNT),
            (
                "parameters a caller can pass by position",
                pl.col("declared_count"),
                Unit.COUNT,
            ),
        ),
        finding_order=pl.col("position") - 1,
        question=pl.concat_str(
            pl.lit("stop `"),
            pl.col("left_name"),
            pl.lit("` and `"),
            pl.col("right_name"),
            pl.lit("` from being interchangeable"),
        ),
        options=(
            "give each one the type it actually names",
            "make the second one keyword-only",
        ),
    )
    return RuleQuery.integer(
        frame,
        pl.col("value"),
        findings=findings,
    )
