from ..... import rule
from .....facts import ModuleCouplingFact
from .....models import (
    Choice,
    CountReport,
    Finding,
    Measurement,
    Reported,
    Unit,
    counted,
)


@rule
def dependency_on_a_less_stable_module(
    subject: ModuleCouplingFact,
    *,
    tolerance: float = 0.0,
) -> CountReport:
    """Count imports this module makes that point toward something less stable than itself.

    Definition
    ----------
    Stability here is not a guess about how often a file changes, it is counted. A module that
    five others import and that imports one itself is hard to change, because five callers feel it,
    and Martin writes that as instability `I = Ce / (Ca + Ce)`, which is zero when nothing can push
    a change into the module and one when everything can. The Stable Dependencies Principle says an
    arrow must point toward stability, so an import from a module with a low `I` to a module with a
    higher one is reported, and `tolerance` is the slack a project allows before a difference
    counts.

    This is a layering violation found without anybody naming a layer. A written contract in a
    configuration file states which package may import which, and it rots the first time somebody
    adds a legitimate edge and widens the rule to keep the build green, until the file describes
    the code instead of constraining it. The dependency graph already says which modules the
    repository leans on, so the constraint can be derived every run and cannot drift away from what
    the code does.

    Evidence
    --------
    Each finding names the importing module, the imported module, the instability of both as a
    percentage, and how many modules depend on the importer, which is what says how far a change
    travels. The repair is a choice between inverting the arrow and moving what the two share, and
    both are decisions somebody has to make. The value is the number of this module's imports that
    point the wrong way.

    Exceptions
    ----------
    Only imports between modules this repository owns are read, since a third-party package has no
    instability inside this architecture. A module in an import cycle is stable and unstable at
    once and the two sides of the cycle each report the other, so `ALL-ARCH0011` is the rule to fix
    first and this one settles afterward. A plugin a framework loads by name is imported by nothing
    static, so it reads as maximally unstable and its dependencies are judged accordingly, which is
    correct rather than a false positive.

    Examples
    --------
    Bad
    ~~~
    `codec.py` is imported by eight modules and imports two, so `I` is `0.2`. It imports `cli.py`,
    which imports six modules and is imported by none, so `I` is `1.0`. Every edit to the command
    line can now reach the codec, and through it the eight modules that depend on the codec. This
    returns `1`.

    Good
    ~~~~
    `cli.py` imports `codec.py`. The arrow runs from the volatile module to the settled one, so a
    change to the command line reaches nothing and a change to the codec is a decision somebody
    made deliberately. This returns `0`.

    References
    ----------
    Cites "Agile Software Development", the Stable Dependencies Principle
    Cites "Clean Architecture", chapter 14, component coupling
    Cites "Design Principles and Design Patterns"
    https://web.archive.org/web/20150906155800/http://www.objectmentor.com/resources/articles/Principles_and_Patterns.pdf
    Cites "JDepend", the tool that first computed these metrics over a package graph
    https://github.com/clarkware/jdepend
    """
    volatile = [
        dependency
        for dependency in subject.dependencies
        if dependency.instability > subject.instability + tolerance
    ]
    return Reported(
        value=len(volatile),
        findings=tuple(
            Finding(
                message=(
                    f"`{subject.module}` sits at {subject.instability * 100:.3g} percent "
                    f"instability and imports `{dependency.module}` at "
                    f"{dependency.instability * 100:.3g} percent instability, so every change "
                    "to the second one "
                    f"reaches the {counted(subject.afferent_count, 'module')} that depend on "
                    f"the first"
                ),
                span=subject.span,
                measurements=(
                    Measurement(
                        name="instability of the importer",
                        value=subject.instability * 100.0,
                        unit=Unit.PERCENTAGE,
                    ),
                    Measurement(
                        name="instability of the imported",
                        value=dependency.instability * 100.0,
                        unit=Unit.PERCENTAGE,
                    ),
                    Measurement(
                        name="modules depending on the importer", value=subject.afferent_count
                    ),
                ),
                repair=Choice(
                    question=(
                        f"turn the arrow from `{subject.module}` to `{dependency.module}` around"
                    ),
                    options=(
                        "invert it through a contract the settled module owns",
                        "move what they share into a module both can depend on",
                    ),
                ),
            )
            for dependency in volatile
        ),
    )
