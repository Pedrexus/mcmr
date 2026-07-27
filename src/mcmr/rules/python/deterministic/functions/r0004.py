from ..... import rule
from .....facts import FunctionFact
from .....models import Count


@rule
def unjustified_positional_only_parameter_count(
    subject: FunctionFact,
    *,
    allowed_names: tuple[str, ...] = (),
) -> Count:
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
    return sum(
        parameter.is_positional_only
        and not parameter.is_receiver
        and not parameter.is_required_by_external_contract
        and parameter.name not in allowed_names
        for parameter in subject.parameters
    )
