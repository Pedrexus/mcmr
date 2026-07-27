from ..... import rule
from .....facts import ModuleSurfaceFact, SourceSpan
from .....models import Choice, CountReport, Finding, Measurement, Reported


@rule
def non_erasable_construct(subject: ModuleSurfaceFact) -> CountReport:
    """Count the constructs that stop TypeScript from being erased rather than compiled.

    Definition
    ----------
    Count the declarations whose meaning survives type stripping, which are an `enum`, a `const
    enum`, a runtime `namespace`, a constructor parameter property, and `import =`. Each generates
    JavaScript rather than disappearing with the types, which is why a runtime that strips types
    cannot run them and why TypeScript 5.8 added `erasableSyntaxOnly` to find them.

    The cost is not only the build step. An `enum` produces an object with a reverse mapping that
    JSON never round-trips, a `namespace` produces a closure that tree shaking cannot open, and a
    parameter property hides a field declaration inside a signature.

    Evidence
    --------
    Each finding names the construct, its kind, and the line it is written on, counted against the
    module's own length. The repair is a choice, since rewriting the construct and deciding this
    project never strips types are both real answers. The value is the number found.

    Exceptions
    ----------
    A project that compiles through a bundler and never intends to strip types can keep them, and
    should say so by disabling this rule rather than by leaving it failing. A declaration file
    describing an external library states constructs it does not own.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: typescript

       enum Status { Active = 'ACTIVE' }
       class Engine { constructor(private limit: number) {} }

    Good
    ~~~~
    .. code-block:: typescript

       const Status = { Active: 'ACTIVE' } as const;
       type Status = (typeof Status)[keyof typeof Status];

    References
    ----------
    Cites "TypeScript documentation", 5.8 release notes, the `erasableSyntaxOnly` option
    https://www.typescriptlang.org/docs/handbook/release-notes/typescript-5-8.html
    Cites "Node.js documentation", type stripping
    https://nodejs.org/api/typescript.html
    Cites "TypeScript documentation", handbook, enums and their runtime output
    https://www.typescriptlang.org/docs/handbook/enums.html
    """
    return Reported(
        value=len(subject.erasable_violations),
        findings=tuple(
            Finding(
                message=(
                    f"`{construct.name or subject.span.path}` is a "
                    f"{construct.kind.replace('_', ' ')}, which generates JavaScript rather than "
                    f"disappearing with the types"
                ),
                span=SourceSpan(
                    path=subject.span.path,
                    start_line=construct.line,
                    end_line=construct.line,
                ),
                measurements=(
                    Measurement(
                        name="constructs stripping cannot erase",
                        value=len(subject.erasable_violations),
                    ),
                    Measurement(name="lines in the module", value=subject.physical_line_count),
                ),
                repair=Choice(
                    question=f"decide what `{construct.name or construct.kind}` is for",
                    options=(
                        "state it as a value this language can erase around",
                        "turn this rule off in a project that always compiles",
                    ),
                ),
            )
            for construct in subject.erasable_violations
        ),
    )
