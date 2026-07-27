from ..... import rule
from .....facts import ImportBindingFact
from .....models import Replace, SourceRewrite


@rule
def internal_relative_import(
    subject: ImportBindingFact,
) -> bool:
    """Detect an absolute import of a module owned by the current project package.

    Definition
    ----------
    Index Python modules below the configured source roots, including namespace-package prefixes
    that have no `__init__.py`. Inspect selected files for absolute `import` and `from` statements
    whose resolved module belongs to the same top-level project package as the importing module.
    Derive the relative level from the current package and longest common dotted prefix. The
    Boolean result identifies one qualifying statement. The default policy prefers relative
    imports.

    Evidence
    --------
    Each finding records the imported project modules and source range. A safe UTF-8 text edit is
    attached when the statement is single-line, the relative level is unique, and all local names
    remain unchanged. Aliased module imports can be rewritten as `from` imports. Unaliased dotted
    imports are reported without an edit because they bind the package root rather than the final
    module name.

    Exceptions
    ----------
    Keep absolute imports across different top-level packages, for unresolved modules, or when a
    public executable intentionally supports direct invocation outside its package. Relative
    imports already in use, wildcard imports, standalone top-level modules, mixed import lists,
    generated files, and excluded paths receive no automatic edit. Package-root `from` imports
    are supported, while a bare `import package` has no binding-preserving relative equivalent.

    Examples
    --------
    Bad
    ~~~
    Inside `acme/features/service.py`, `from acme.models import User` and
    `import acme.tools.formatting as formatting` are internal absolute imports.

    Good
    ~~~~
    `from ...models import User`, `from ...tools import formatting as formatting`, and
    `import httpx` preserve an explicit package boundary.

    References
    ----------
    Cites "PEP 328, Imports and Relative Imports"
    https://peps.python.org/pep-0328/
    Cites "The Python Language Reference", the import statement
    https://docs.python.org/3.14/reference/simple_stmts.html#the-import-statement
    Cites "The Python Language Reference", Namespace packages
    https://docs.python.org/3.14/reference/import.html#namespace-packages
    """
    return (
        subject.is_project_owned
        and not subject.is_relative
        and not subject.is_wildcard
        and not subject.is_generated
        and not subject.is_vendored
    )


@internal_relative_import.fix(is_default=True)
def use_relative_import(
    subject: ImportBindingFact,
) -> list[SourceRewrite]:
    """State the same module through the shortest equivalent relative path."""
    if subject.module_node is None or not subject.importer_module:
        return []
    package = subject.importer_module.split(".")[:-1]
    target = subject.module.split(".")
    pairs = list(zip(package, target, strict=False))
    shared = next(
        (index for index, (left, right) in enumerate(pairs) if left != right),
        len(pairs),
    )
    dots = "." * (len(package) - shared + 1)
    return [Replace(target=subject.module_node, source=dots + ".".join(target[shared:]))]
