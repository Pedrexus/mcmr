from ..... import rule
from .....facts import ModuleSurfaceFact
from .....models import Choice, CountReport, Finding, Measurement, Reported, counted


@rule
def relative_import_depth(subject: ModuleSurfaceFact) -> CountReport:
    """Measure how far a module climbs out of its own directory to find what it imports.

    Definition
    ----------
    Return the greatest number of parent directories any one import in this module traverses. A
    path that climbs three levels is telling you the two files belong to different parts of the
    system and somebody reached across anyway. It also breaks the moment either file moves, which
    is why the depth, rather than any single import, is the measurement worth having.

    Evidence
    --------
    The finding names the module and the deepest specifier it imports through, with the number of
    directories that specifier climbs. The repair is a choice, since an alias and a move fix the
    same climb differently. The value is that depth.

    Exceptions
    ----------
    A test that reaches into the tree it exercises climbs by design. A project with configured path
    aliases should see zero here, because an alias states the boundary the climb was hiding, which
    is the usual repair.

    Examples
    --------
    `import { User } from '../../../models/user'` returns `3` and wants an alias or a move.
    `import { User } from './models/user'` returns `0`.

    References
    ----------
    Cites "TypeScript documentation", handbook, module resolution and path mapping
    https://www.typescriptlang.org/docs/handbook/modules/reference.html
    Adapts typescript-eslint no-restricted-imports
    https://typescript-eslint.io/rules/no-restricted-imports/
    Cites "Clean Architecture", boundaries and dependency direction
    """
    if not subject.deepest_relative_import:
        return Reported(value=0)
    return Reported(
        value=subject.deepest_relative_import,
        findings=(
            Finding(
                message=(
                    f"`{subject.span.path}` imports through "
                    f"`{subject.deepest_relative_specifier}`, which climbs "
                    f"{counted(subject.deepest_relative_import, 'directory', 'directories')} out "
                    f"of its own"
                ),
                span=subject.span,
                measurements=(
                    Measurement(
                        name="directories it climbs", value=subject.deepest_relative_import
                    ),
                ),
                repair=Choice(
                    question=f"stop `{subject.span.path}` reaching across the tree to import",
                    options=(
                        "declare a path alias for the boundary the climb crosses",
                        "move whichever of the two files is in the wrong place",
                    ),
                ),
            ),
        ),
    )
