from mcmr.facts import DirectoryFact, ImportBindingFact, ModuleFact, NodeRef, SourceSpan
from mcmr.models import FixSafety, Remove, Replace
from mcmr.rules.general.deterministic.filesystem.r0001 import empty_directories
from mcmr.rules.general.deterministic.filesystem.r0002 import package_depth
from mcmr.rules.general.deterministic.filesystem.r0003 import directory_module_count
from mcmr.rules.general.deterministic.modules.r0001 import module_line_count
from mcmr.rules.general.deterministic.modules.r0002 import module_member_count
from mcmr.rules.python.deterministic.imports.r0001 import (
    internal_relative_import,
    use_relative_import,
)
from mcmr.rules.python.deterministic.imports.r0002 import project_private_import
from mcmr.rules.python.deterministic.imports.r0003 import (
    remove_unused_import,
    unused_import,
)
from mcmr.rules.python.deterministic.modules.r0003 import non_init_reexport_module

SERVICE = SourceSpan(path="src/acme/service.py")
EXAMPLE = SourceSpan(path="example.py")


def binding(span: SourceSpan, name: str, module: str, **traits: bool) -> ImportBindingFact:
    """Return one import binding of a name out of a module, located in the given file."""
    return ImportBindingFact.model_validate(
        {"key": "import", "span": span, "name": name, "module": module} | traits
    )


def test_project_owned_import_cases() -> None:
    """A project-owned import is read for how far it reaches and for how private its target is.

    An absolute path into a sibling module and a component the package marked private are the two
    shapes, and a binding the project does not own carries neither of them.
    """
    absolute = binding(SERVICE, "User", "acme.models", is_project_owned=True)
    assert internal_relative_import(absolute) == 1
    assert internal_relative_import(absolute.model_copy(update={"is_relative": True})) == 0
    assert (
        internal_relative_import(
            absolute.model_copy(update={"is_external": True, "is_project_owned": False})
        )
        == 0
    )

    addressed = absolute.model_copy(
        update={
            "importer_module": "acme.api.service",
            "module_node": NodeRef(id="module", span=SERVICE, text="acme.models"),
        }
    )
    plan = use_relative_import(addressed)
    assert plan is not None
    assert [rewrite.source for rewrite in plan.rewrites if isinstance(rewrite, Replace)] == [
        "..models"
    ]
    assert use_relative_import(absolute) is None

    private = binding(
        SERVICE,
        "execute",
        "acme._engine",
        is_project_owned=True,
        has_private_module_component=True,
    )
    assert project_private_import(private) == 1
    constant = private.model_copy(
        update={
            "has_private_module_component": False,
            "is_private_member": True,
            "is_private_uppercase_constant": True,
        }
    )
    assert project_private_import(constant) == 0


def test_unused_import_cases() -> None:
    """A binding is unused while nothing reads it and nothing else explains why it stays.

    The edit is offered where deleting the statement is the whole repair and nowhere else. A
    statement binding several names would lose the live ones with the dead one, and a package
    initializer states a surface its own module never reads, so both are reported with no edit.
    """
    unused = binding(EXAMPLE, "json", "json")
    assert unused_import(unused).value
    assert not unused_import(unused.model_copy(update={"reference_count": 1})).value
    assert not unused_import(unused.model_copy(update={"is_reexported": True})).value
    assert not unused_import(unused.model_copy(update={"is_wildcard": True})).value
    assert not unused_import(unused.model_copy(update={"has_documented_side_effect": True})).value
    assert not unused_import(
        unused.model_copy(update={"module": "__future__", "name": "annotations"})
    ).value

    declaration = NodeRef(id="import", span=EXAMPLE, text="import json")
    alone = unused.model_copy(update={"declaration": declaration, "is_sole_binding": True})
    plan = remove_unused_import(alone)
    assert plan is not None
    assert list(plan.rewrites) == [Remove(target=declaration)]
    assert remove_unused_import(alone.model_copy(update={"is_sole_binding": False})) is None
    assert remove_unused_import(alone.model_copy(update={"declaration": None})) is None
    assert (
        remove_unused_import(alone.model_copy(update={"span": SourceSpan(path="a/__init__.py")}))
        is None
    )
    assert remove_unused_import.safety is FixSafety.REVIEW


def test_directory_cases() -> None:
    empty = DirectoryFact(key="directory", span=SourceSpan(path="src/unused"))
    assert empty_directories(empty)
    assert not empty_directories(empty.model_copy(update={"is_ignored": True}))
    assert package_depth(empty.model_copy(update={"source_depth": 6})) == 6
    crowded = empty.model_copy(update={"direct_module_count": 7})
    assert directory_module_count(crowded) == 7
    assert directory_module_count(crowded.model_copy(update={"is_definition_catalog": True})) == 0
    assert (
        directory_module_count(
            crowded.model_copy(update={"is_definition_catalog": True}),
            allow_definition_catalogs=False,
        )
        == 7
    )


def test_module_shape_cases() -> None:
    module = ModuleFact(
        key="module",
        span=SourceSpan(path="src/models.py"),
        physical_line_count=401,
        class_count=9,
        function_count=4,
        has_only_imports_and_all=True,
    )
    assert module_line_count(module).value == 401
    assert module_member_count(module) == 13
    assert non_init_reexport_module(module) == 1
    assert (
        non_init_reexport_module(module.model_copy(update={"is_package_initializer": True})) == 0
    )
