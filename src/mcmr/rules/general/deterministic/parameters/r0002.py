from ..... import rule
from .....facts import ParameterFact
from .....models import Choice, CountReport, Finding, Measurement, Reported, counted


@rule
def configuration_object_parameter(
    subject: ParameterFact, *, minimum_reads: int = 2
) -> CountReport:
    """Count parameters a callable only reads attributes from.

    Definition
    ----------
    Report a parameter whose every resolved use is an attribute read, and which is read for at
    least `minimum_reads` distinct names. Such a parameter does not need the object, only those
    values. Taking the whole object hides which parts the callable depends on, forces every caller
    and every test to build a complete object, and couples the callable to a type it never uses as
    a type.

    Evidence
    --------
    Each finding names the callable, the parameter, its declared type, and every attribute name
    the body reads from it, since those names are the narrower contract the callable actually
    wants. The repair is a choice, because a settings object a framework hands over is not one a
    caller can unpack. The value is the number of such parameters.

    Exceptions
    ----------
    A parameter with any use other than an attribute read is skipped, because the callable then
    depends on the object itself. A parameter whose uses could not all be resolved is skipped
    rather than guessed. Reading many attributes is legitimate when the callable is the owner of
    that type, such as a serializer or a repository, and a project can raise `minimum_reads` or
    disable the rule where a settings object is the deliberate contract.

    Examples
    --------
    A function that reads only `config.host` and `config.port` returns `1` and should take those
    two values. A function that reads `config.host` and also passes `config` onward returns `0`.

    References
    ----------
    Cites "Refactoring", replace parameter with explicit methods
    Cites "Clean Code", function arguments
    Cites "Implementation Patterns", on revealing intent in signatures
    """
    unpacked = [
        parameter
        for parameter in subject.parameters
        if parameter.all_uses_known
        and not parameter.operations
        and len(set(parameter.attribute_reads)) >= minimum_reads
    ]
    return Reported(
        value=len(unpacked),
        findings=tuple(
            Finding(
                message=(
                    f"`{parameter.owner}` takes `{parameter.name}` as a whole `"
                    f"{parameter.annotation}` and reads only "
                    f"{', '.join(f'`{name}`' for name in sorted(set(parameter.attribute_reads)))}"
                ),
                span=parameter.span or subject.span,
                measurements=(
                    Measurement(name="attributes read", value=len(set(parameter.attribute_reads))),
                    Measurement(name="other operations on it", value=len(parameter.operations)),
                ),
                repair=Choice(
                    question=(
                        f"pass `{parameter.owner}` the "
                        f"{counted(len(set(parameter.attribute_reads)), 'value')} it reads"
                    ),
                    options=(
                        "take them as explicit parameters",
                        "keep the object where a framework owns its shape",
                    ),
                ),
            )
            for parameter in unpacked
        ),
    )
