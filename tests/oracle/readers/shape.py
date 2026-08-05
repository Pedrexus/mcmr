from patos import FrozenModel


class Shape(FrozenModel):
    """One source shape and which of its own lines a reader is expected to keep reporting.

    The answer travels with the shape rather than being read back out of the source afterwards, so
    a property built from these states an opinion of its own instead of only comparing two readers
    of the same text. `opening` holds what has to stay at the top of a file, such as an import or
    an include, and `body` holds the rest. `reported` indexes into the two concatenated, so a shape
    states its answer wherever the answer sits.
    """

    opening: list[str] = []
    body: list[str] = []
    reported: set[int] = set()
