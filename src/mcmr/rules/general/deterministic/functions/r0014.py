from ..... import rule
from .....facts import FunctionFact
from .....models import Choice, CountReport, Finding, Measurement, Reported, counted


@rule
def required_parameter_count(subject: FunctionFact) -> CountReport:
    """Count the inputs a caller must supply to one callable.

    Definition
    ----------
    Count the declared parameters that carry no default and are not the receiver. A long required
    list is the readable symptom of a callable that owns several responsibilities, or of a missing
    type that should carry the values together. The count excludes optional parameters because a
    caller never has to think about them, and excludes the receiver because it is not a decision
    the caller makes.

    Evidence
    --------
    The finding records the callable range, every counted parameter by name, and how many of the
    declared parameters those required ones are. It is stated for every callable rather than only
    for a wide one, because the measurement is the whole answer and a reader has to be able to see
    which inputs it counted. The value is the number of required inputs.

    Exceptions
    ----------
    A constructor that assembles a value from its parts, a mathematical function over independent
    scalars, and a framework entry point with a fixed contract all legitimately take several
    inputs. The count is a measurement and the policy owns the ceiling.

    Examples
    --------
    `def render(template, context, encoding="utf-8")` returns `2`. A method whose only parameter is
    its receiver returns `0`.

    References
    ----------
    Generalizes Clippy too_many_arguments
    https://rust-lang.github.io/rust-clippy/master/index.html#too_many_arguments
    Generalizes typescript-eslint max-params
    https://typescript-eslint.io/rules/max-params/
    Cites Pylint R0913 too-many-arguments
    https://pylint.readthedocs.io/en/stable/user_guide/messages/refactor/too-many-arguments.html
    """
    required = [
        parameter.name
        for parameter in subject.parameters
        if not parameter.is_receiver and parameter.is_required_by_external_contract
    ]
    named = ", ".join(f"`{name}`" for name in required)
    return Reported(
        value=len(required),
        findings=(
            Finding(
                message=(
                    f"`{subject.name}` cannot be called without {named}, which is "
                    f"{counted(len(required), 'parameter')} of the "
                    f"{len(subject.parameters)} it declares"
                    if required
                    else f"`{subject.name}` can be called with nothing, since none of the "
                    f"{counted(len(subject.parameters), 'parameter')} it declares is required"
                ),
                span=subject.span,
                measurements=(
                    Measurement(name="parameters a caller has to supply", value=len(required)),
                    Measurement(name="parameters declared", value=len(subject.parameters)),
                ),
                repair=Choice(
                    question=f"ask `{subject.name}` for less",
                    options=(
                        "group the inputs that always travel together into one type",
                        "default the ones a caller almost never chooses",
                    ),
                ),
            ),
        ),
    )
