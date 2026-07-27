from ..... import rule
from .....facts import ModuleSurfaceFact
from .....models import Choice, CountReport, Finding, Measurement, Reported


@rule
def star_reexport_surface(subject: ModuleSurfaceFact) -> CountReport:
    """Count the wholesale re-exports that turn a module's internals into its public API.

    Definition
    ----------
    Count `export *` declarations in one module. Each one publishes everything the file it names
    happens to export, now and after every future edit. A helper added for one caller becomes part
    of the module's contract the moment it is exported, and no reviewer sees that happen. The
    module then cannot be refactored safely, because nobody knows which of its internals somebody
    outside came to depend on.

    A barrel that names its exports states a contract. A barrel that stars them states a wish.

    Evidence
    --------
    Each finding names one wholesale re-export and the module it publishes, counted against the
    named exports beside it so a reader can see how much of the surface is stated and how much is
    inherited. The repair is a choice, since naming the exports and declaring the barrel a real
    public API are both real answers. The value is the number of wholesale re-exports.

    Exceptions
    ----------
    A package root that deliberately re-publishes a subpackage is a real public API and belongs in
    a project's exclusions. A generated index is regenerated rather than edited, so a project
    excludes the generator's output instead of the generator.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: typescript

       export * from './UserService';
       export * from './internal/userValidation';

    Good
    ~~~~
    .. code-block:: typescript

       export { UserService } from './services/UserService';
       export type { UserDTO } from './dto/UserDTO';

    References
    ----------
    Cites "TypeScript documentation", handbook, modules and re-exports
    https://www.typescriptlang.org/docs/handbook/2/modules.html
    Cites "typescript-eslint documentation", no-restricted-imports and module boundary guidance
    https://typescript-eslint.io/rules/no-restricted-imports/
    Cites "eslint-plugin-boundaries documentation", declaring allowed import directions
    https://github.com/javierbrea/eslint-plugin-boundaries
    """
    return Reported(
        value=subject.star_reexport_count,
        findings=tuple(
            Finding(
                message=(
                    f"`{subject.span.path}` re-exports everything `{specifier}` happens to "
                    f"export, so a helper added there joins this module's contract unreviewed"
                ),
                span=subject.span,
                measurements=(
                    Measurement(name="wholesale re-exports", value=subject.star_reexport_count),
                    Measurement(
                        name="named re-exports beside them", value=subject.named_reexport_count
                    ),
                ),
                repair=Choice(
                    question=f"say what `{subject.span.path}` means to publish from `{specifier}`",
                    options=(
                        "name the exports this module actually offers",
                        "exclude a package root that deliberately republishes a subpackage",
                    ),
                ),
            )
            for specifier in subject.star_reexports
        ),
    )
