from ..... import rule
from .....facts import LifetimeAnnotation, RustSurfaceFact, SourceSpan
from .....models import Choice, CountReport, Finding, Measurement, Reported

# The two declarations Rust states elision rules for. A type, a trait, and an alias each name a
# lifetime the compiler never infers on their behalf, so there is nothing to compare an annotation
# against and nothing this rule can honestly say about one.
_ELIDING_KINDS = frozenset({"function", "method"})


@rule
def elidable_lifetime_annotation(subject: RustSurfaceFact) -> CountReport:
    """Count lifetime annotations the compiler would have inferred on its own.

    Definition
    ----------
    Read every signature that names a lifetime and report one whose elided form means exactly the
    same thing. Elision gives each input lifetime position its own fresh lifetime and gives every
    elided output the receiver's lifetime, so an annotation restating that tells the reader nothing
    the compiler did not already know and charges them the reading anyway.

    The cost is not the character count. A signature carrying `<'a>` reads as a signature with a
    borrowing constraint worth understanding, so the reader stops and works out which one. Doing
    that and finding nothing is worse than never having stopped.

    Two arrangements are claimed and both are settled by the signature alone. A lifetime written
    in exactly one input position and read nowhere else is one elision produces identically. A
    lifetime the receiver carries and the return states is another, since elision hands every
    elided output the receiver's lifetime whatever else is in scope.

    Evidence
    --------
    Each finding names the declaration, the lifetimes it states, and the line it states them on,
    and counts the input positions those lifetimes appear in. The repair is a choice, because
    deleting the annotation and keeping it for a reason the signature cannot show are both real
    answers. The value is the number of annotations elision would have produced identically.

    Exceptions
    ----------
    A type, a trait, and an alias are not judged at all, because Rust states no elision rule for
    any of them and there is nothing to compare their annotation against.

    A lifetime written in two input positions is never reported even where it reaches no output,
    because tying two inputs together is a constraint elision cannot state and the two signatures
    therefore do not mean the same thing. Where the body relies on the tie, deleting the annotation
    does not compile at all.

    An output lifetime coming from one input with no receiver is left alone as well. It turns on
    how many lifetime positions the inputs hold in total, and a bare `Node` hides one where `&str`
    shows it, so the arity lives in the type definitions rather than in the signature. Clippy reads
    those definitions and reports that arrangement, and guessing at it here would mean reporting a
    signature that does not compile without its annotation.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: rust

       fn name<'a>(&'a self) -> &'a str { ... }
       fn width<'a>(text: &'a str) -> usize { ... }

    Good
    ~~~~
    .. code-block:: rust

       fn name(&self) -> &str { ... }
       fn width(text: &str) -> usize { ... }

    A lifetime that survives is one elision would get wrong, such as
    `fn pick<'a>(&self, other: &'a str) -> &'a str`, where the elided output would borrow from
    `self` instead, or `fn descend<'a>(node: &'a Node, found: &mut Vec<&'a Node>)`, where both
    inputs have to name one lifetime for the body to compile at all.

    References
    ----------
    Cites "The Rust Reference", lifetime elision
    https://doc.rust-lang.org/reference/lifetime-elision.html
    Cites "Rust API Guidelines", C-STRUCT-BOUNDS and the cost of stating what is inferred
    https://rust-lang.github.io/api-guidelines/future-proofing.html
    Cites "corrode", do not worry about lifetimes
    https://corrode.dev/blog/lifetimes/
    """
    idle = [annotation for annotation in subject.annotations if is_elidable(annotation)]
    return Reported(
        value=len(idle),
        findings=tuple(
            Finding(
                message=(
                    f"`{annotation.owner}` names {stated(annotation)}, which elision would have "
                    f"produced on its own"
                ),
                span=SourceSpan(
                    path=subject.span.path,
                    start_line=annotation.line,
                    end_line=annotation.line,
                ),
                measurements=(
                    Measurement(name="lifetimes it states", value=len(annotation.names)),
                    Measurement(name="input positions naming one", value=positions(annotation)),
                ),
                repair=Choice(
                    question=(
                        f"say what `{annotation.owner}` gains from writing {stated(annotation)}"
                    ),
                    options=(
                        "delete the annotation and let elision state the same signature",
                        "keep it where a reader needs the borrow named",
                    ),
                ),
            )
            for annotation in idle
        ),
    )


def stated(annotation: LifetimeAnnotation) -> str:
    """Return the lifetimes one declaration names, as a reader would read them back."""
    return ", ".join(f"`'{name}`" for name in annotation.names)


def positions(annotation: LifetimeAnnotation) -> int:
    """Return how many input positions one declaration names any of its lifetimes in."""
    return len(annotation.parameters) + bool(annotation.receiver)


def is_elidable(annotation: LifetimeAnnotation) -> bool:
    """Decide whether elision would have produced the signature this one wrote out.

    Only a function and a method are judged, since those are the two declarations Rust states
    elision rules for, and an annotation the compiler never infers cannot be one it would have
    inferred. An annotation is elidable only where every lifetime it declares is.
    """
    if annotation.kind not in _ELIDING_KINDS or not annotation.names:
        return False
    return all(is_inferred(annotation, name) for name in annotation.names)


def is_inferred(annotation: LifetimeAnnotation, name: str) -> bool:
    """Decide whether elision would place one named lifetime exactly where it is written.

    Elision gives every input position its own lifetime, so a name written in one input position
    and read nowhere else is one it produces identically, and a name written in two ties them
    together in a way elision cannot state. Elision then hands each elided output the receiver's
    lifetime, so a return naming the receiver's own lifetime and nothing else is produced
    identically too. Everything else is either a constraint elision would drop or an arrangement
    the signature alone cannot settle.
    """
    if name == "static" or name in annotation.beyond:
        return False
    inputs = annotation.parameters.count(name) + (annotation.receiver == name)
    if name not in annotation.returned:
        return inputs == 1
    return annotation.receiver == name and inputs == 1 and set(annotation.returned) == {name}
