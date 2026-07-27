from ..... import rule
from .....facts import OverrideFact
from .....models import Count


@rule
def ancestor_count(subject: OverrideFact) -> Count:
    """Measure how many types sit above one class in its inheritance chain.

    Definition
    ----------
    Count every distinct ancestor above the class this link derives, resolved or not, and report it
    once per class at the link to its first declared base. Each ancestor is a place a method a
    reader is looking at might actually live, so the count is how far a reader may have to walk to
    find one. A diamond names its shared ancestor once, because a reader visits it once.

    An inheritance link is the only fact that can answer this, since the base of a class usually
    lives in another file and only a resolved chain across the whole repository knows what sits
    above it. Reporting at the first declared base is what keeps one class one finding when it
    inherits from several.

    Depth is a measurement rather than a defect, and a project policy owns the ceiling. A framework
    that asks a project to derive from three of its own layers before adding one is a different
    situation from a hierarchy a project grew itself, and only the project can say which it has.

    Evidence
    --------
    Each finding records the derived class range, its declared bases, and every ancestor name above
    it. The value is the number of distinct ancestors. Any link other than the one to the first
    declared base measures zero, so the class is counted once.

    Exceptions
    ----------
    Ancestors this repository does not declare are counted by name but their own ancestors are not,
    since nothing here can read them. A class whose bases are all external therefore has no
    inheritance link at all and is not judged, which is deliberate, because a chain a project does
    not own is not a chain it can shorten.

    Examples
    --------
    Given `class Row: ...`, `class Record(Row): ...`, and `class Report(Record): ...`, `Record`
    measures `1` and `Report` measures `2`. `Row` declares no base at all, so it has no inheritance
    link and is not measured rather than measuring zero. A `class Both(Record, Row)` still measures
    `2`, because `Row` is one ancestor whichever path reaches it, and it is counted at the link to
    `Record` alone.

    References
    ----------
    Generalizes Pylint R0901 too-many-ancestors
    https://pylint.readthedocs.io/en/stable/user_guide/messages/refactor/too-many-ancestors.html
    Generalizes SonarSource S110
    https://rules.sonarsource.com/java/RSPEC-110/
    Cites "Effective Java", favor composition over inheritance
    Cites "Design Patterns", on the cost of deep class hierarchies
    """
    first = subject.base_names[0] if subject.base_names else ""
    if subject.depth != 1 or first != subject.base.rsplit(".", 1)[-1]:
        return 0
    return len(subject.ancestor_names)
