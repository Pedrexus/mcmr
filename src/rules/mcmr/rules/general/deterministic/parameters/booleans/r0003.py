import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import FunctionFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import FunctionRelation, Table

# What a Boolean is called in each language a frontend fills. A parameter typed with any of these
# reads as a flag at the call site whatever its name is.
_BOOLEAN = ["bool", "boolean", "Boolean", "_Bool", "BOOL"]


@rule("ALL-PARA0003")
def positional_boolean_parameter(subject: Table[FunctionFact]) -> CountQuery:
    """Count Boolean parameters a caller must pass by position.

    Definition
    ----------
    Report a parameter typed Boolean that a caller cannot name at the call site. The call then
    reads `render(document, True, False)`, which says nothing about what is true, and a reader has
    to open the signature to find out. Worse, the two flags can be transposed and the program keeps
    compiling, so the mistake surfaces as behavior rather than as an error.

    The repair is not always a keyword argument. Two Booleans usually mean the function does two
    things, and splitting it removes the flags along with the ambiguity.

    Evidence
    --------
    Each finding names the function, the parameter, and its position. The value is the number of
    positional Boolean parameters.

    Exceptions
    ----------
    A parameter a language forces into position, such as the receiver, is not counted. A signature
    an external contract fixes, like a framework callback, is a reason to exclude the module rather
    than to fight the interface. A single Boolean whose name reads as a sentence at the call site,
    such as `sorted(values, reverse)`, is the borderline case this rule deliberately still reports,
    because the next Boolean added beside it is the one that breaks.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       def render(document, inline: bool, minified: bool): ...

       render(document, True, False)

    Good
    ~~~~
    .. code-block:: python

       def render(document, *, inline: bool, minified: bool): ...

       render(document, inline=True, minified=False)

    The same shape in Rust is `fn render(document: &Document, inline: bool, minified: bool)`, and
    the same repair is a small options struct or two functions.

    References
    ----------
    Cites "Refactoring", remove flag argument
    https://refactoring.com/catalog/removeFlagArgument.html
    Cites "Clean Code", chapter 3, flag arguments
    Generalizes Ruff FBT001 boolean-type-hint-positional-argument
    Generalizes Ruff FBT002 boolean-default-value-positional-argument
    """
    trapped = subject.lazy(FunctionRelation.PARAMETERS).filter(
        (pl.col("type_name").is_in(_BOOLEAN) | pl.col("has_boolean_annotation"))
        & ~pl.col("is_keyword_only")
        & ~pl.col("is_receiver")
    )
    counts = trapped.group_by("function_id").agg(pl.len().cast(pl.UInt64).alias("value"))
    frame = (
        subject.lazy(FunctionRelation.FUNCTIONS)
        .join(counts, left_on="entity_id", right_on="function_id", how="left")
        .with_columns(pl.col("value").fill_null(0))
    )
    finding_rows = trapped.join(counts, on="function_id", how="inner").join(
        subject.lazy(FunctionRelation.FUNCTIONS),
        left_on="function_id",
        right_on="entity_id",
        how="inner",
    )
    position = pl.col("ordinal") + 1
    findings = FindingQuery.build(
        finding_rows,
        pl.concat_str(
            pl.lit("`"),
            pl.col("name_right"),
            pl.lit("` takes Boolean parameter `"),
            pl.col("name"),
            pl.lit("` in position "),
            position,
            pl.lit(", where a call passes its value without its name"),
        ),
        (
            ("position in the parameter list", position, Unit.COUNT),
            ("Boolean parameters passed by position", pl.col("value"), Unit.COUNT),
        ),
        finding_order=pl.col("ordinal"),
        question=pl.concat_str(
            pl.lit("make `"),
            pl.col("name"),
            pl.lit("` say what its Boolean value means"),
        ),
        options=(
            "require its name at the call site",
            "replace the flag with a named behavior",
            "split the callable",
        ),
    )
    return RuleQuery.integer(
        frame,
        pl.col("value"),
        findings=findings,
    )
