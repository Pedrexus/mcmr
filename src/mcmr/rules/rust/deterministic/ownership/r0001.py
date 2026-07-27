from ..... import rule
from .....facts import RustSurfaceFact, SourceSpan
from .....models import Choice, CountReport, Finding, Measurement, Reported


@rule
def clone_inside_loop(subject: RustSurfaceFact) -> CountReport:
    """Count copies made once per iteration rather than once.

    Definition
    ----------
    Report each `clone` or `to_owned` written inside a `for`, `while`, or `loop` body. Owning data
    instead of borrowing it is a fair trade at the edge of a function and a bad one in the middle
    of a loop, because the price is paid again on every pass and the loop is exactly where it is
    least visible. A copy hoisted above the loop, or a borrow that lives across it, costs once.

    This is the counterpart to the lifetime rules. Removing an annotation by owning the data is
    usually right, and this is the one place where it usually is not.

    Evidence
    --------
    Each finding names the value copied, the function it sits in, the line, and how deeply nested
    the loop around it is. The repair is a choice, because hoisting the copy and borrowing across
    the loop are different edits and only the body says which one holds. The value is the number of
    copies made inside a loop.

    Exceptions
    ----------
    A copy of something the loop then consumes, such as an owned value handed to a spawned task or
    pushed into a collection that outlives the iteration, is a copy that has to happen. A cheap
    copy of a small value is a copy the compiler often removes, and measuring is what settles it.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: rust

       for item in items {
           registry.insert(prefix.clone(), item);
       }

    Good
    ~~~~
    .. code-block:: rust

       let prefix = prefix.clone();
       for item in items {
           registry.insert(prefix.as_str(), item);
       }

    References
    ----------
    Cites Clippy redundant_clone
    https://rust-lang.github.io/rust-clippy/master/index.html#redundant_clone
    Cites "The Rust Performance Book", allocations in hot loops
    https://nnethercote.github.io/perf-book/heap-allocations.html
    Cites "corrode", do not worry about lifetimes
    https://corrode.dev/blog/lifetimes/
    """
    repeated = [clone for clone in subject.clones if clone.loop_depth > 0]
    return Reported(
        value=len(repeated),
        findings=tuple(
            Finding(
                message=(
                    f"`{clone.owner or subject.span.path}` copies "
                    f"`{clone.receiver or 'a value'}` inside a loop, so the copy is paid again on "
                    f"every pass"
                ),
                span=SourceSpan(
                    path=subject.span.path, start_line=clone.line, end_line=clone.line
                ),
                measurements=(
                    Measurement(name="loops around it", value=clone.loop_depth),
                    Measurement(name="copies this module makes", value=len(subject.clones)),
                ),
                repair=Choice(
                    question=(
                        f"pay for `{clone.receiver or 'this value'}` once rather than once a pass"
                    ),
                    options=(
                        "hoist the copy above the loop",
                        "borrow across the loop instead",
                        "keep it where the loop consumes what it copied",
                    ),
                ),
            )
            for clone in repeated
        ),
    )
