from ..... import rule
from .....facts import ModuleCouplingFact
from .....models import (
    Choice,
    Finding,
    Measurement,
    OccurrenceReport,
    Reported,
    Unit,
    counted,
)


@rule
def concrete_module_the_repository_leans_on(
    subject: ModuleCouplingFact,
    *,
    minimum_dependents: int = 3,
    minimum_distance: float = 0.7,
) -> OccurrenceReport:
    """Report a module many others depend on that offers them nothing to implement against.

    Definition
    ----------
    Martin places every module on two axes. Instability `I` is the share of its coupling that
    points outward and abstractness `A` is the share of its types that state a contract, and the
    main sequence is the line `A + I = 1` running from abstract and depended upon to concrete and
    depending. Distance from it is `D = |A + I - 1|`, and the far corner on the concrete side is
    the zone of pain, where a module everything imports is made entirely of implementations.

    That corner is reported here. `minimum_dependents` keeps a module nothing depends on out of it,
    and `minimum_distance` is how far past the line the module has to sit. The remedy is not to
    split the module, it is to give its callers something abstract to depend on instead.

    Evidence
    --------
    The finding names the module, where the repository states it, how many modules depend on it,
    how many of its types are contracts out of how many it declares, and its distance from the
    main sequence as a percentage of the furthest a module can sit. The repair is a choice, since
    a shared record and a module that wants an interface look identical from here. The value is
    whether this module sits in that corner.

    Exceptions
    ----------
    A data model is deliberately concrete and deliberately shared, and so is a value type or a
    settings module, so a repository whose central types are records rather than behavior will find
    these here and should exclude them rather than wrap them in interfaces nobody needs. A module
    whose types come from a code generator is not one a reader can restructure. A language that
    states no contract construct reads as fully concrete for the same reason a file of plain
    functions does, which is that it has none, so C sources and anything a frontend outside the
    repository graph produced are not judged here at all.

    Examples
    --------
    Bad
    ~~~
    `models.py` declares forty concrete classes, thirty modules import it, and it imports one. `A`
    is `0.0` and `I` is about `0.03`, so `D` is `0.97` and every one of those thirty modules is
    wired to the exact shape of forty classes. This returns `true`.

    Good
    ~~~~
    `protocol.py` declares three protocols and no implementation, thirty modules import it, and it
    imports one. `A` is `1.0` and `I` is about `0.03`, so `D` is `0.03`. The thirty modules are
    wired to three promises instead. This returns `false`.

    References
    ----------
    Cites "Agile Software Development", the Stable Abstractions Principle and the main sequence
    Cites "Clean Architecture", chapter 14, component coupling
    Cites "Design Principles and Design Patterns"
    https://web.archive.org/web/20150906155800/http://www.objectmentor.com/resources/articles/Principles_and_Patterns.pdf
    Cites "JDepend", the tool that first computed these metrics over a package graph
    https://github.com/clarkware/jdepend
    """
    painful = (
        subject.afferent_count >= minimum_dependents
        and subject.abstractness + subject.instability < 1.0
        and subject.distance >= minimum_distance
    )
    if not painful:
        return Reported(value=False)
    return Reported(
        value=True,
        findings=(
            Finding(
                message=(
                    f"`{subject.module}` is imported by "
                    f"{counted(subject.afferent_count, 'module')} and "
                    f"{subject.abstract_declaration_count} of the "
                    f"{counted(subject.declaration_count, 'type')} it declares state a "
                    f"contract, so every one of those importers is wired to an implementation"
                ),
                span=subject.span,
                measurements=(
                    Measurement(name="modules depending on it", value=subject.afferent_count),
                    Measurement(name="types it declares", value=subject.declaration_count),
                    Measurement(
                        name="of them stating a contract", value=subject.abstract_declaration_count
                    ),
                    Measurement(
                        name="distance from the main sequence",
                        value=subject.distance * 100.0,
                        unit=Unit.PERCENTAGE,
                    ),
                ),
                repair=Choice(
                    question=(
                        f"give the {counted(subject.afferent_count, 'importer')} of "
                        f"`{subject.module}` something abstract to depend on"
                    ),
                    options=(
                        "extract the contract its callers actually use",
                        "exclude a module whose types are deliberately records",
                    ),
                ),
            ),
        ),
    )
