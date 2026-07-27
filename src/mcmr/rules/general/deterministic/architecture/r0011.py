from ..... import rule
from .....facts import DependencyComponentFact, DependencyEdge, SourceSpan
from .....graph import DirectedGraph, GraphEdge
from .....models import (
    Choice,
    CountReport,
    Finding,
    Measurement,
    Reported,
    counted,
)


@rule
def import_cycles(subject: DependencyComponentFact) -> CountReport:
    """Count the groups of modules that import each other, directly or through a chain.

    Definition
    ----------
    Build strongly connected components from the import edges the repository graph resolved
    between modules this repository owns. Report each component holding at least two modules, plus
    any module that explicitly imports itself, as one cycle. An import of a package nobody here can
    edit is not an edge, and neither a call nor an inheritance is read.

    The unit is the component rather than the loop. A component of eight modules holds many
    distinct paths around itself, and counting those would report one tangle as dozens of findings
    that one decision resolves together. Pylint answers the other question and enumerates the
    paths, so five `R0401` messages there and one component here describe the same tangle.

    Evidence
    --------
    Each finding names the modules of one component and one import inside it, located at the file
    and line the repository states that import on. The repair is a choice, since breaking a cycle
    is an architectural decision rather than an edit anybody can prove right. The value is the
    number of cyclic components.

    Exceptions
    ----------
    None by default. A project may ignore the rule or configure an accepted maximum while it
    removes an established cycle. An import written only inside a type-checking block is not an
    edge, since it does not exist while the program runs, which is exactly the shape a project
    reaches for when it has already broken a cycle deliberately.

    Examples
    --------
    Bad
    ~~~
    `package.a` imports `package.b` while `package.b` imports `package.a`, so neither module can be
    read, tested, or moved without the other. This returns `1`. Eight modules reaching each other
    through a chain are one component and also return `1`, because one decision separates them.

    Good
    ~~~~
    Two modules that only import a common third module return `0`, and so does a repository whose
    modules never import each other.

    References
    ----------
    Generalizes Pylint R0401 cyclic-import
    Adapts Pylint C0415 import-outside-toplevel
    Cites "Clean Architecture", component coupling principles
    Cites "Large-Scale C++ Software Design", dependency cycles
    Cites "Exploring the Structure of Complex Software Designs"
    """
    cycles = DirectedGraph(
        edges=[GraphEdge(source=edge.source, target=edge.target) for edge in subject.import_edges]
    ).cyclic_components()
    return Reported(
        value=len(cycles),
        findings=tuple(tangle(members, subject.import_edges) for members in cycles),
    )


def tangle(members: tuple[str, ...], edges: list[DependencyEdge]) -> Finding:
    """State one cyclic component, located at an import that runs inside it.

    Naming every module is what says how large the decision is, and locating the finding at one
    arrow rather than at all of them is deliberate, since no single import is more to blame than
    the others and a report naming twenty equally arbitrary lines is one nobody reads.
    """
    held = set(members)
    inside = [edge for edge in edges if edge.source in held and edge.target in held]
    at = inside[0]
    return Finding(
        message=(
            f"{counted(len(members), 'module')} import each other in one cycle, which are "
            f"{', '.join(f'`{member}`' for member in members)}, and `{at.source}` importing "
            f"`{at.target}` is one of the {counted(len(inside), 'arrow')} closing it"
        ),
        span=SourceSpan(path=at.path, start_line=at.line, end_line=at.line),
        measurements=(
            Measurement(name="modules in the cycle", value=len(members)),
            Measurement(name="imports inside it", value=len(inside)),
        ),
        repair=Choice(
            question=f"break the cycle holding `{at.source}` and `{at.target}`",
            options=(
                "move what the modules share into one both can depend on",
                "invert an arrow through a contract the depended-upon module owns",
                "defer an import to the type-checking block where only a type is needed",
            ),
        ),
    )
