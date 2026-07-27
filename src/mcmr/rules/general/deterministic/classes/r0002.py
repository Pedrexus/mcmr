from ..... import rule
from .....facts import ClassFact, MemberKind, MethodAnalysis, SourceSpan, Visibility
from .....models import Choice, CountReport, Finding, Measurement, Reported, counted


@rule
def class_method_order(
    subject: ClassFact,
    *,
    lifecycle: tuple[str, ...] = (
        "__init_subclass__",
        "__new__",
        "__init__",
        "__post_init__",
        "model_post_init",
    ),
    visibility_order: tuple[str, ...] = (
        Visibility.PUBLIC,
        Visibility.PROTECTED,
        Visibility.INTERNAL,
        Visibility.PRIVATE,
    ),
    kind_order: tuple[str, ...] = (
        MemberKind.CONSTRUCTOR,
        MemberKind.PROPERTY,
        MemberKind.STATIC_METHOD,
        MemberKind.CLASS_METHOD,
        MemberKind.METHOD,
    ),
    alphabetical: bool = True,
) -> CountReport:
    """Count classes whose methods do not follow one explicit source order.

    Definition
    ----------
    Inspect methods declared directly in each class. Put the configured lifecycle names first in
    their declared sequence, then the language protocol members a provider marks as such. Order
    every remaining method by visibility, then by member kind, then case-insensitively by name when
    `alphabetical` is true. A `# region` boundary or its language equivalent starts a new
    independently ordered section. Accessors that share one name, such as a property setter beside
    its getter, stay stable. The value is the number of classes whose current order differs.

    Every language that declares members inside a type takes part. A provider maps its own spelling
    onto the shared visibility and member kinds, so a Java `private static` helper, a Rust
    associated function, a TypeScript `#field` accessor, and a Python `classmethod` all sort under
    one declared policy rather than a Python-shaped category list.

    Evidence
    --------
    Each finding names the class, its range in the file, and the first member that sits
    somewhere other than where the declared order puts it, beside how many members the class
    declares and how many of them are out of place. The repair is a choice rather than an edit,
    since only the author knows whether an order was deliberate. Lifecycle names, visibility
    order, and kind order are all configurable, and a member whose visibility or kind is left out
    of the configured order sorts after every configured one. `visibility_order` and `kind_order`
    are the two sorts applied after
    the lifecycle names, so a project that puts protected members first or class methods before
    properties states that order rather than accepting this one. The value is the number of classes
    whose declared order differs from the expected one.

    Exceptions
    ----------
    Decorators execute while a class body is built, and one declaration can refer to an earlier
    descriptor. This rule offers no automatic reorder. Keep required adjacency or execution order
    by splitting the class or introducing named regions. Disable WPS338 and CCE001 when this
    stricter policy owns the same class. Alphabetical order is a project preference rather than a
    language requirement.

    Examples
    --------
    A public property followed by `__init__` is reported because lifecycle methods come first.
    Public methods `save` and `open` are reported when alphabetical ordering is enabled because
    `open` precedes `save`. A property getter immediately followed by its setter remains stable.

    References
    ----------
    Generalizes wemake-python-styleguide WPS338
    https://wemake-python-styleguide.readthedocs.io/en/latest/pages/usage/violations/consistency.html
    Generalizes flake8-class-attributes-order CCE001
    https://github.com/best-doctor/flake8-class-attributes-order
    Cites "Google Java Style Guide", ordering of class contents
    https://google.github.io/styleguide/javaguide.html#s3.4.2-ordering-class-contents
    """
    findings: list[Finding] = []
    for item in subject.classes:
        for region in sorted({method.region for method in item.methods}):
            methods = [method for method in item.methods if method.region == region]
            expected = sorted(
                methods,
                key=lambda method: method.order_key(
                    lifecycle=lifecycle,
                    visibility_order=visibility_order,
                    kind_order=kind_order,
                    alphabetical=alphabetical,
                ),
            )
            if methods == expected:
                continue
            findings.append(misordered(item.name, item.span or subject.span, methods, expected))
            break
    return Reported(value=len(findings), findings=tuple(findings))


def misordered(
    owner: str,
    span: SourceSpan,
    declared: list[MethodAnalysis],
    expected: list[MethodAnalysis],
) -> Finding:
    """Return what one class out of order states, named at the first member that moved.

    The first difference is the one a reader acts on. Listing every member that shifted would
    mostly list members carried along by the one that is genuinely in the wrong place.
    """
    moved = [
        left.name for left, right in zip(declared, expected, strict=True) if left is not right
    ]
    first = next(
        index
        for index, pair in enumerate(zip(declared, expected, strict=True))
        if pair[0] is not pair[1]
    )
    return Finding(
        message=(
            f"`{owner}` declares {len(moved)} of its "
            f"{counted(len(declared), 'member')} out of order, and "
            f"`{expected[first].name}` belongs where `{declared[first].name}` sits"
        ),
        span=span,
        measurements=(
            Measurement(name="declared members", value=len(declared)),
            Measurement(name="members out of place", value=len(moved)),
        ),
        repair=Choice(
            question=f"put `{expected[first].name}` before `{declared[first].name}`",
            options=("reorder the members", "open a named region where this order is deliberate"),
        ),
    )
