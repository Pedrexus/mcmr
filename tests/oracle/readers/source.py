from hypothesis import strategies as st
from patos import FrozenModel

from .shape import Shape


class Source(FrozenModel):
    """One generated source and the lines a reader is expected to report in it."""

    text: str
    reported: set[int]


@st.composite
def assembled(
    draw: st.DrawFn,
    shapes: list[Shape],
    *,
    prologue: list[str] | None = None,
    limit: int = 6,
) -> Source:
    """Build one source out of independent shapes and state which of its lines stay reported.

    Every shape names its own declarations, so any subset of them concatenates into a source that
    still says what each of them means. The openings gather at the top in the order they were drawn
    and the bodies follow, which is what a language demanding its imports first requires and what
    every other language tolerates.
    """
    if not all(isinstance(shape, Shape) for shape in shapes):
        raise TypeError("assembled sources require source shapes")
    drawn = draw(st.lists(st.sampled_from(shapes), min_size=1, max_size=limit, unique_by=id))
    opening = [] if prologue is None else list(prologue)
    openings: list[int] = []
    for shape in drawn:
        openings.append(len(opening) + 1)
        opening.extend(shape.opening)
    body: list[str] = []
    bodies: list[int] = []
    for shape in drawn:
        body.extend(("", ""))
        bodies.append(len(opening) + len(body) + 1)
        body.extend(shape.body)
    return Source(
        text="\n".join([*opening, *body, ""]),
        reported={
            openings[index] + offset
            if offset < len(shape.opening)
            else bodies[index] + offset - len(shape.opening)
            for index, shape in enumerate(drawn)
            for offset in shape.reported
        },
    )
