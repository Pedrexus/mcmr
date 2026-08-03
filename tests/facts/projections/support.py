import ast
from pathlib import Path
from typing import TYPE_CHECKING

from mcmr.structure.projections import (
    Dependency,
    ModuleGraph,
)

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping


def chain() -> ModuleGraph:
    """Build a layered repository by hand, where `a` imports `b` imports `c`."""
    return ModuleGraph(
        root=Path("/repository"),
        paths={"pkg": "pkg/__init__.py", **{f"pkg.{name}": f"pkg/{name}.py" for name in "abc"}},
        dependencies=(
            Dependency(importer="pkg.a", imported="pkg.b", path="pkg/a.py", lines=(1,)),
            Dependency(importer="pkg.b", imported="pkg.c", path="pkg/b.py", lines=(1, 4)),
        ),
    )


def tangle() -> ModuleGraph:
    """Build a repository whose `a`, `b`, and `c` import each other, with `e` above them."""
    return ModuleGraph(
        root=Path("/repository"),
        paths={f"pkg.{name}": f"pkg/{name}.py" for name in "abcde"},
        dependencies=(
            Dependency(importer="pkg.a", imported="pkg.b", path="pkg/a.py", lines=(1,)),
            Dependency(importer="pkg.b", imported="pkg.c", path="pkg/b.py", lines=(1,)),
            Dependency(importer="pkg.c", imported="pkg.a", path="pkg/c.py", lines=(1,)),
            Dependency(importer="pkg.c", imported="pkg.d", path="pkg/c.py", lines=(2,)),
            Dependency(importer="pkg.e", imported="pkg.a", path="pkg/e.py", lines=(1,)),
        ),
    )


def repository(tmp_path: Path) -> Path:
    """Write one small package whose imports form a layering, and return its root."""
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "engine.py").write_text(
        "from .store import load\n\n\ndef run():\n    return load()\n"
    )
    (package / "store.py").write_text("import json\n\n\ndef load():\n    return json.dumps({})\n")
    (package / "cli.py").write_text("from .engine import run\n\n\ndef main():\n    return run()\n")
    return tmp_path


def exported_targets(
    root: Path,
    imported: str,
    *,
    requested: Collection[str],
    modules: Collection[str],
    seen: Collection[str] = (),
) -> set[str]:
    """Follow explicit package reexports to the modules that declare requested names."""
    key = f"{imported}|{'|'.join(sorted(requested))}"
    if key in seen:
        return {imported} & set(modules)
    package_init = root.joinpath(*imported.split("."), "__init__.py")
    source = (
        package_init
        if package_init.exists()
        else root.joinpath(*imported.split(".")).with_suffix(".py")
    )
    if not source.exists():
        return {imported} & set(modules)
    package = imported if source == package_init else imported.rpartition(".")[0]
    aliases = (
        (exported, alias)
        for exported in ast.parse(source.read_text()).body
        if isinstance(exported, ast.ImportFrom)
        for alias in exported.names
        if (alias.asname or alias.name) in requested
    )
    targets = {
        target
        for exported, alias in aliases
        for target in exported_targets(
            root,
            resolved(exported, package),
            requested={alias.name},
            modules=modules,
            seen=[*seen, key],
        )
    }
    return targets or ({imported} & set(modules))


def type_only_targets(
    root: Path,
    statement: ast.ImportFrom,
    imported: str,
    modules: Collection[str],
) -> set[str]:
    """Return the concrete module targets Archy assigns to one type-only import."""
    requested = {alias.name for alias in statement.names}
    return exported_targets(root, imported, requested=requested, modules=modules)


def type_only_dependencies(root: Path, modules: Collection[str]) -> set[tuple[str, str]]:
    """Return the module pairs Archy derives from imports under `TYPE_CHECKING`."""
    found: set[tuple[str, str]] = set()
    for path in sorted(root.rglob("*.py")):
        parts = path.relative_to(root).with_suffix("").parts
        module = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
        package = module if parts[-1] == "__init__" else module.rsplit(".", 1)[0]
        guarded_imports = (
            statement
            for guard in ast.walk(ast.parse(path.read_text()))
            if isinstance(guard, ast.If) and is_type_checking_guard(guard.test)
            for statement in ast.walk(guard)
            if isinstance(statement, ast.ImportFrom)
        )
        for statement in guarded_imports:
            imported = resolved(statement, package)
            found.update(
                (module, target)
                for target in type_only_targets(root, statement, imported, modules)
            )
    return found


def package_import_dependencies(
    root: Path,
    modules: Collection[str],
    paths: Mapping[str, str],
) -> set[tuple[str, str]]:
    """Return runtime imports whose target is a package rather than a leaf module.

    Archy omits some `from package import name` edges when `package` is represented by an
    `__init__.py`. MCMR keeps them because executing the statement executes that package.
    """

    def found_in(path: Path) -> set[tuple[str, str]]:
        """Return every import-from pair one source file states."""
        parts = path.relative_to(root).with_suffix("").parts
        module = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
        package = module if parts[-1] == "__init__" else module.rsplit(".", 1)[0]
        return {
            (module, resolved(statement, package))
            for statement in ast.walk(ast.parse(path.read_text()))
            if isinstance(statement, ast.ImportFrom)
        }

    type_only = type_only_dependencies(root, modules)
    pairs = set().union(*(found_in(path) for path in sorted(root.rglob("*.py"))))
    return {
        pair
        for pair in pairs - type_only
        if pair[1] in modules and paths[pair[1]].endswith("/__init__.py")
    }


def transitive_dependencies(
    dependencies: Collection[tuple[str, str]],
) -> set[tuple[str, str]]:
    """Expand immediate import hops into the declarations explicit reexports reach."""
    closure = set(dependencies)
    frontier = set(dependencies)
    while frontier:
        additions = {
            (importer, target)
            for importer, imported in frontier
            for source, target in dependencies
            if imported == source
        } - closure
        closure.update(additions)
        frontier = additions
    return closure


def reexported_surface_dependencies(
    surface: Collection[tuple[str, str]],
    *,
    resolved: Collection[tuple[str, str]],
) -> set[tuple[str, str]]:
    """Find immediate surfaces replaced by the declarations their imports reach."""
    reachable = transitive_dependencies(surface)
    targets_by_source: dict[str, set[str]] = {}
    for source, target in reachable:
        targets_by_source.setdefault(source, set()).add(target)
    targets_by_importer: dict[str, set[str]] = {}
    for importer, target in resolved:
        targets_by_importer.setdefault(importer, set()).add(target)
    return {
        pair
        for pair in set(surface) - set(resolved)
        if targets_by_source.get(pair[1], set()) & targets_by_importer.get(pair[0], set())
    }


def archy_graphs(root: Path, ours: ModuleGraph) -> tuple[ModuleGraph, ModuleGraph]:
    """Return Archy's `408679b` graph and the graph without its native-stub fallback."""
    modules = {
        "mcmr",
        "mcmr.api",
        "mcmr.backend",
        "mcmr.engine",
        "mcmr.engine.runtime",
        "mcmr.models",
        "mcmr.queries",
    }
    pairs = {
        ("mcmr", "mcmr.queries"),
        ("mcmr.api", "mcmr"),
        ("mcmr.api", "mcmr.backend"),
        ("mcmr.api", "mcmr.engine.runtime"),
        ("mcmr.api", "mcmr.models"),
        ("mcmr.api", "mcmr.queries"),
        ("mcmr.engine", "mcmr.engine.runtime"),
    }
    paths = {module: ours.paths[module] for module in modules}
    dependencies = [
        Dependency(importer=importer, imported=imported, path=paths[importer])
        for importer, imported in sorted(pairs)
    ]
    stub_modules = {module for module, path in ours.paths.items() if path.endswith(".pyi")}
    stub_fallbacks = {
        (edge.importer, edge.imported.rpartition(".")[0])
        for edge in ours.dependencies
        if edge.imported in stub_modules
    } | {
        (importer, imported.rpartition(".")[0])
        for importer, imported in type_only_dependencies(root, set(ours.paths))
        if imported in stub_modules
    }
    comparable = [
        dependency
        for dependency in dependencies
        if (dependency.importer, dependency.imported) not in stub_fallbacks
    ]
    return (
        ModuleGraph(root=root, paths=paths, dependencies=dependencies),
        ModuleGraph(root=root, paths=paths, dependencies=comparable),
    )


def is_type_checking_guard(test: ast.expr) -> bool:
    """Whether one `if` test is the `TYPE_CHECKING` guard, spelled either way."""
    return any(
        (isinstance(node, ast.Name) and node.id == "TYPE_CHECKING")
        or (isinstance(node, ast.Attribute) and node.attr == "TYPE_CHECKING")
        for node in ast.walk(test)
    )


def resolved(statement: ast.ImportFrom, package: str) -> str:
    """Return the module one import names, resolving a relative one against its own package."""
    if not statement.level:
        return statement.module or ""
    owner = package.split(".")
    kept = owner[: len(owner) - statement.level + 1]
    return ".".join([*kept, statement.module] if statement.module else kept)
