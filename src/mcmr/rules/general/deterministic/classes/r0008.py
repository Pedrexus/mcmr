from collections import Counter

from ..... import rule
from .....facts import SymbolReachFact
from .....models import Count


@rule
def declared_field_count(subject: SymbolReachFact) -> Count:
    """Measure the widest data surface one type in this module declares.

    Definition
    ----------
    Group every data member this module declares by the type that owns it and return the largest
    group. A data member is state a reader has to hold in mind for every method of the type, so the
    width of the widest type is what says whether the file asks too much. Counting is by resolved
    declaration rather than by syntax, so a name a type states once in its body and again in its
    initializer is one member, not two.

    Every language that attaches state to a type takes part, and each one spells the declaration
    differently. A Rust struct field, a TypeScript property, a C++ member, a Python class-body
    annotation, and a Python initializer assigning to `self` all arrive as the same resolved
    declaration, so one measurement covers them.

    Reading the whole module at once is what makes the measure affordable. Ownership comes from the
    qualified name each declaration already carries, so nothing has to be re-resolved and a type
    split across an interface and its implementation still counts once.

    Evidence
    --------
    Each finding records the module range and every data member grouped under the type declaring
    it. The value is the size of the largest group.

    Exceptions
    ----------
    Callables are counted by the neighbouring public-method rule, because a wide record and a wide
    interface are two different defects. A module declaring no type at all measures zero. The count
    is a measurement, and a project policy owns the ceiling, since a serialized message and a
    service object tolerate very different widths.

    Examples
    --------
    A class whose initializer assigns `self.host`, `self.port`, and `self.timeout` returns `3`, and
    a dataclass stating the same three names as annotations returns `3` as well. A class stating
    `host: str` in its body and assigning `self.host` in its initializer counts `host` once, so it
    returns `1`. A module declaring only functions returns `0`.

    References
    ----------
    Adapts Pylint R0902 too-many-instance-attributes
    https://pylint.readthedocs.io/en/stable/user_guide/messages/refactor/too-many-instance-attributes.html
    Cites Clippy struct_field_names
    https://rust-lang.github.io/rust-clippy/master/index.html#struct_field_names
    Generalizes SonarSource S1820
    https://rules.sonarsource.com/java/RSPEC-1820/
    Cites "Refactoring", the large class smell
    """
    owners = Counter(
        declaration.qualname.rsplit(".", 1)[0]
        for declaration in subject.declarations
        if declaration.kind == "attribute"
    )
    return max(owners.values(), default=0)
