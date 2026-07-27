from ..... import rule
from .....facts import RustSurfaceFact, SourceSpan
from .....models import Choice, CountReport, Finding, Measurement, Reported


@rule
def demanded_static_lifetime(subject: RustSurfaceFact) -> CountReport:
    """Count parameters and fields that demand data pinned for the whole run of the program.

    Definition
    ----------
    Report each `'static` written as the lifetime of a reference a parameter takes or a field
    holds. A `'static` reference does not say the data lives a long time. It says the data lives
    forever, which is a claim only a literal, a leak, or a global can honestly make, and demanding
    it of a caller is how the annotation wins an argument with the borrow checker by making the
    type unable to hold anything the caller owns.

    Where the pin sits decides whether it costs anything. A parameter typed `&'static str` cannot
    be handed a name read from a file and a field typed the same way cannot store one, and neither
    limitation is visible at the call site until someone tries. A return typed `&'static str` is
    the opposite, since it promises the caller more than it had to, forecloses nothing, and is how
    a lookup table hands back a name without allocating. Only the demanding side is reported.

    Evidence
    --------
    Each finding names the declaration that demands the pin and the line it is written on, and
    states how many pins the module holds in total so a reader can see what share demands. The
    repair is a choice, since owning the data and keeping the pin honestly are both real answers.
    The value is the number of demanding pins.

    Exceptions
    ----------
    A `T: 'static` bound is not counted, because a bound says what a type may not borrow rather
    than pinning any particular value, and a thread, a task, or a trait object often requires one.
    A return position is not counted, because promising a longer lifetime than required takes
    nothing away from a caller. A field that genuinely holds a compile-time table, and an interner
    that leaks on purpose, both demand honestly, and a project excludes those rather than owning
    data it never frees.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: rust

       struct Report { title: &'static str }
       fn describe(name: &'static str) -> Report { ... }

    Good
    ~~~~
    .. code-block:: rust

       struct Report { title: String }
       fn describe(name: &str) -> Report { ... }

    A `fn label(kind: Kind) -> &'static str` returning one of a fixed set of names is not reported,
    because the names really do live in the binary and the caller gains by being told so.

    References
    ----------
    Cites "The Rust Reference", static lifetime
    https://doc.rust-lang.org/reference/lifetime-elision.html#static-lifetime-elision
    Cites "Rust by Example", the static lifetime and its two meanings
    https://doc.rust-lang.org/rust-by-example/scope/lifetime/static_lifetime.html
    Cites "corrode", do not worry about lifetimes
    https://corrode.dev/blog/lifetimes/
    """
    demanding = [pin for pin in subject.pins if pin.position == "demand"]
    return Reported(
        value=len(demanding),
        findings=tuple(
            Finding(
                message=(
                    f"`{pin.owner or subject.span.path}` demands a `'static` reference, so no "
                    f"caller can hand it anything read at run time"
                ),
                span=SourceSpan(path=subject.span.path, start_line=pin.line, end_line=pin.line),
                measurements=(
                    Measurement(name="pins demanding here", value=len(demanding)),
                    Measurement(name="pins this module states", value=len(subject.pins)),
                ),
                repair=Choice(
                    question=f"decide what `{pin.owner or subject.span.path}` may be handed",
                    options=(
                        "take an owned value so a caller can build one",
                        "keep the pin where only a literal or a leak can honestly satisfy it",
                    ),
                ),
            )
            for pin in demanding
        ),
    )
