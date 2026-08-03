import polars as pl

from ..... import rule
from .....facts import FunctionFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table import FunctionRelation, Table


@rule("PY-FUNC0001")
def unjustified_positional_only_parameter_count(
    subject: Table[FunctionFact],
    *,
    allowed_names: tuple[str, ...] = (),
) -> CountQuery:
    """Count positional-only parameters without an observable structural reason.

    Definition
    ----------
    Inspect module functions and direct methods that use `/`. Treat the marker as justified for a
    magic method, an explicit `@override`, a function that also accepts arbitrary keyword
    arguments, or a configured compatibility name. Report every other positional-only parameter
    except `self` and `cls`. The result is the number of reported parameters.

    Evidence
    --------
    Each finding identifies the function and names its positional-only parameters. The rule uses
    syntax that is stable across runs and does not infer whether a name feels semantically useful.
    The value is the number of positional-only parameters with no structural reason.

    Exceptions
    ----------
    Builtin or C API parity, a published compatibility contract, deliberately unnamed mathematical
    operands, and functions passed as callbacks are excluded. Additional compatibility names can
    be added through `allowed_names`. Nested local functions are outside this public interface
    check.

    Examples
    --------
    Bad
    ~~~
    `def load_document(path, /)` hides a meaningful public name without a collision or override.

    Good
    ~~~~
    `def lookup(name, /, **keywords)` permits `name` to appear independently in `keywords`.
    `def __eq__(self, other, /)` follows a magic method contract.

    References
    ----------
    Cites "The Python Tutorial", Special parameters
    https://docs.python.org/3.14/tutorial/controlflow.html#special-parameters
    Cites "PEP 570, Positional-Only Parameters"
    https://peps.python.org/pep-0570/
    """
    candidates = (
        subject.lazy(FunctionRelation.PARAMETERS)
        .filter(
            pl.col("is_positional_only")
            & ~pl.col("is_receiver")
            & ~pl.col("is_required_by_external_contract")
            & ~pl.col("name").is_in(list(allowed_names))
        )
        .group_by("function_id")
        .agg(pl.len().cast(pl.UInt64).alias("value"))
    )
    frame = (
        subject.lazy(FunctionRelation.FUNCTIONS)
        .join(
            candidates,
            left_on="entity_id",
            right_on="function_id",
            how="left",
        )
        .with_columns(pl.col("value").fill_null(0))
    )
    value = pl.col("value")
    return RuleQuery.integer(
        frame,
        value,
        findings=FindingQuery.precise_integer(
            frame, value, "unjustified positional only parameter count"
        ),
    )
