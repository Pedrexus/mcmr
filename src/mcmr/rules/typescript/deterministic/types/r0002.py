from ..... import rule
from .....facts import ModuleSurfaceFact, SourceSpan
from .....models import (
    Choice,
    Finding,
    Measurement,
    PercentageReport,
    Reported,
    Unit,
    counted,
)

# What each hatch is called in a sentence, since a rule reading a kind has to say it in words a
# reader recognizes from their own source rather than as the field name the provider used.
NAMED = {
    "assertion": "type assertion",
    "non_null": "non-null assertion",
    "any": "`any`",
    "ignore_comment": "suppression comment",
}


@rule
def escape_hatch_density(subject: ModuleSurfaceFact) -> PercentageReport:
    """Measure how much of a module steps around what its type system proved.

    Definition
    ----------
    Return the share of lines carrying a type assertion, a non-null assertion, an `any`, or a
    suppression comment. Each one is a promise to the compiler with nothing behind it, and the
    compiler stops checking exactly where the promise was made. One is a considered decision. A
    module where a tenth of the lines make one has stopped being typed, and no per-occurrence rule
    says so, because each occurrence looked reasonable on its own.

    Evidence
    --------
    Each finding names one hatch, its kind, and the line it sits on, beside the module's own length
    and the share every hatch together comes to. The repair is a choice, since validating at the
    boundary and excluding a declaration file are different answers to the same reading. The value
    is that share.

    Exceptions
    ----------
    A boundary that receives untyped data legitimately asserts once it has validated, and a schema
    validator is the usual way to make that assertion earn its keep. A declaration file describing
    an untyped library is assertions by nature. Both belong in a project's exclusions rather than
    in a raised ceiling.

    Examples
    --------
    A 200-line module with two assertions returns `1.0`. The same module with forty returns `20.0`
    and is no longer type checked in any meaningful sense.

    References
    ----------
    Generalizes typescript-eslint no-explicit-any
    Generalizes typescript-eslint no-non-null-assertion
    https://typescript-eslint.io/rules/no-explicit-any/
    Cites "TypeScript documentation", handbook, type assertions and their limits
    https://www.typescriptlang.org/docs/handbook/2/everyday-types.html#type-assertions
    Cites "Zod documentation", validating what the type system cannot prove at runtime
    https://zod.dev/
    """
    if not subject.physical_line_count:
        return Reported(value=0.0)
    share = len(subject.escape_hatches) / subject.physical_line_count * 100.0
    return Reported(
        value=share,
        findings=tuple(
            Finding(
                message=(
                    f"`{subject.span.path}` states a {NAMED[hatch.kind]} here, one of "
                    f"{counted(len(subject.escape_hatches), 'place')} it steps around its own "
                    f"types"
                ),
                span=SourceSpan(
                    path=subject.span.path, start_line=hatch.line, end_line=hatch.line
                ),
                measurements=(
                    Measurement(name="hatches in the module", value=len(subject.escape_hatches)),
                    Measurement(name="lines in the module", value=subject.physical_line_count),
                    Measurement(name="share of the module", value=share, unit=Unit.PERCENTAGE),
                ),
                repair=Choice(
                    question=(
                        f"give the {NAMED[hatch.kind]} in `{subject.span.path}` something "
                        f"behind it"
                    ),
                    options=(
                        "validate the value and let the type follow from the check",
                        "exclude a declaration file describing an untyped library",
                    ),
                ),
            )
            for hatch in subject.escape_hatches
        ),
    )
