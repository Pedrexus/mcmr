from mcmr.facts import (
    CommentFact,
    CommentGroup,
    ImportBindingFact,
    ModuleFact,
    NodeRef,
    SourceSpan,
    SyntaxFact,
    SyntaxNode,
)
from mcmr.rules.general.deterministic.comments.r0006 import unresolved_work_marker
from mcmr.rules.general.deterministic.functions.r0015 import reflective_scope_read
from mcmr.rules.general.deterministic.modules.r0004 import non_ascii_source_path
from mcmr.rules.python.deterministic.classes.r0014 import dynamic_super_receiver
from mcmr.rules.python.deterministic.imports.r0004 import relative_import_beyond_package

SPAN = SourceSpan(path="src/engine.py")


def comments(*texts: str) -> CommentFact:
    """Build one file's comment groups, each carrying the source it spans."""
    return CommentFact(
        key="comments:src/engine.py",
        span=SPAN,
        groups=[
            CommentGroup(
                line_count=len(text.splitlines()) or 1,
                character_count=len(text),
                token_count=len(text.split()),
                node=NodeRef(id=f"comment:{index}", span=SPAN, kind="comment", text=text),
            )
            for index, text in enumerate(texts)
        ],
    )


def declaration(qualname: str, tree: SyntaxNode, kind: str = "callable") -> SyntaxFact:
    """Build one declaration's syntax fact around a tree a rule reads."""
    return SyntaxFact(
        key=f"syntax:src/engine.py:{qualname}",
        span=SPAN,
        language="python",
        qualname=qualname,
        kind=kind,
        source=tree.text,
        tree=tree,
    )


def super_call(*arguments: SyntaxNode) -> SyntaxNode:
    """Build the `super(...).member()` shape, which nests the call under a member access."""
    return SyntaxNode(
        kind="member",
        name="run",
        children=[
            SyntaxNode(
                kind="call",
                name="super",
                children=[SyntaxNode(kind="name", name="super"), *arguments],
            )
        ],
    )


def relative(text: str, importer: str, path: str) -> ImportBindingFact:
    """Build one relative import binding as the kernel states it."""
    span = SourceSpan(path=path)
    return ImportBindingFact(
        key=f"import:{path}:thing",
        span=span,
        name="thing",
        module="thing",
        importer_module=importer,
        is_relative=True,
        declaration=NodeRef(id=f"import:{path}", span=span, kind="import", text=text),
    )


def test_a_marker_opening_a_comment_is_counted_in_any_language() -> None:
    """A note left in place of the work is the same unpaid debt whichever language wrote it."""
    subject = comments("# TODO: handle the empty case", "// FIXME broken\n/* XXX later */")

    assert unresolved_work_marker(subject) == 3
    assert unresolved_work_marker(subject, markers=("todo",)) == 1


def test_a_marker_inside_a_sentence_is_prose_about_the_work() -> None:
    """`# rewrite the todo list` describes the code, and Pylint reads it the same way."""
    assert unresolved_work_marker(comments("# rewrite the todo list")) == 0
    assert unresolved_work_marker(comments("# HACK: pin the version")) == 1


def test_a_trailing_marker_beside_code_still_counts() -> None:
    """A group spans from the first comment to the last, so it carries the code between them."""
    subject = comments("# FIXME: encoding\n    return value  # XXX later")

    assert unresolved_work_marker(subject) == 2


def test_a_group_with_no_retained_source_is_not_read() -> None:
    """A group whose node the provider did not fill states no text to search."""
    subject = comments("# TODO: one").model_copy(
        update={"groups": [CommentGroup(line_count=1, character_count=1, token_count=1)]}
    )

    assert unresolved_work_marker(subject) == 0


def test_every_path_component_outside_ascii_is_counted() -> None:
    """An archive, a build system, and a shell each reproduce the whole path, not its last part."""
    both = ModuleFact(key="module:x", span=SourceSpan(path="src/café/lecteur_à_jour.py"))
    directory = ModuleFact(key="module:y", span=SourceSpan(path="src/café/reader.py"))

    assert non_ascii_source_path(both) == 2
    assert non_ascii_source_path(directory) == 1
    assert non_ascii_source_path(ModuleFact(key="module:z", span=SPAN)) == 0


def test_a_callable_reading_its_own_scope_is_reported() -> None:
    """A body handing back its own scope makes every binding in it unprovable to any reader."""
    tree = SyntaxNode(
        kind="callable",
        name="render",
        text="def render(template):",
        children=[
            SyntaxNode(kind="call", name="locals"),
            SyntaxNode(kind="call", name="format"),
        ],
    )

    assert reflective_scope_read(declaration("render", tree)) == 1
    assert reflective_scope_read(declaration("render", tree), reflections=("format",)) == 1
    assert reflective_scope_read(declaration("render", tree), reflections=()) == 0


def test_a_member_call_is_the_project_rather_than_the_builtin() -> None:
    """`self.locals()` is a method somebody wrote, and it opens no scope."""
    tree = SyntaxNode(
        kind="callable", name="run", children=[SyntaxNode(kind="call", name="self.locals")]
    )

    assert reflective_scope_read(declaration("run", tree)) == 0


def test_a_declaration_that_is_not_a_callable_body_is_not_judged() -> None:
    """A type's tree stops at its methods, so a scope read inside one is not in it."""
    tree = SyntaxNode(
        kind="type", name="Engine", children=[SyntaxNode(kind="call", name="locals")]
    )

    assert reflective_scope_read(declaration("Engine", tree, kind="type")) == 0
    assert reflective_scope_read(declaration("run", tree).model_copy(update={"tree": None})) == 0


def test_a_super_argument_computed_from_the_receiver_is_reported() -> None:
    """`super(type(self), self)` restarts the lookup below itself and recurses in a subclass."""
    computed = super_call(
        SyntaxNode(kind="call", name="type"), SyntaxNode(kind="name", name="self")
    )
    reflected = super_call(
        SyntaxNode(kind="member", name="__class__"), SyntaxNode(kind="name", name="self")
    )
    tree = SyntaxNode(kind="callable", name="run", children=[computed, reflected])

    assert dynamic_super_receiver(declaration("Engine.run", tree)) == 2


def test_a_super_argument_naming_a_class_outright_is_left_alone() -> None:
    """Skipping a step through the resolution order on purpose is a legal thing to do."""
    named = super_call(
        SyntaxNode(kind="name", name="Engine"), SyntaxNode(kind="name", name="self")
    )
    zero = super_call()
    tree = SyntaxNode(kind="callable", name="run", children=[named, zero])

    assert dynamic_super_receiver(declaration("Engine.run", tree)) == 0


def test_a_super_object_merely_assigned_is_not_a_lookup() -> None:
    """Pylint reports the member access rather than the construction, and so does this."""
    held = SyntaxNode(
        kind="binding",
        name="held",
        children=[
            SyntaxNode(
                kind="call",
                name="super",
                children=[
                    SyntaxNode(kind="name", name="super"),
                    SyntaxNode(kind="call", name="type"),
                ],
            )
        ],
    )
    tree = SyntaxNode(kind="callable", name="run", children=[held])

    assert dynamic_super_receiver(declaration("Engine.run", tree)) == 0


def test_a_function_outside_a_class_states_no_owner_to_compare() -> None:
    """A bare function calling `super` is a different Pylint message about a different defect."""
    tree = SyntaxNode(kind="callable", name="run", children=[super_call()])

    assert dynamic_super_receiver(declaration("run", tree)) == 0
    assert (
        dynamic_super_receiver(declaration("Engine.run", tree).model_copy(update={"tree": None}))
        == 0
    )


def test_an_import_climbing_past_its_top_level_package_is_reported() -> None:
    """Two dots from a module whose package has one component leaves the tree entirely."""
    beyond = relative("from ..outside import thing", "pkg.module", "pkg/module.py")
    inside = relative("from .sibling import thing", "pkg.module", "pkg/module.py")

    assert relative_import_beyond_package(beyond) is True
    assert relative_import_beyond_package(inside) is False


def test_a_package_initializer_affords_one_more_level_than_its_neighbours() -> None:
    """`pkg/sub/__init__.py` is `pkg.sub` itself, where `pkg/sub/module.py` only sits in it."""
    initializer = relative("from .. import thing", "pkg.sub", "pkg/sub/__init__.py")
    module = relative("from ... import thing", "pkg.sub.module", "pkg/sub/module.py")

    assert relative_import_beyond_package(initializer) is False
    assert relative_import_beyond_package(module) is True


def test_a_module_in_no_package_has_no_top_level_to_exceed() -> None:
    """The interpreter answers a script with a different failure, so this declines to judge it."""
    script = relative("from . import thing", "script", "script.py")
    absolute = relative("import json", "pkg.module", "pkg/module.py").model_copy(
        update={"is_relative": False}
    )
    unstated = relative("from .. import thing", "pkg.module", "pkg/module.py").model_copy(
        update={"declaration": None}
    )

    assert relative_import_beyond_package(script) is False
    assert relative_import_beyond_package(absolute) is False
    assert relative_import_beyond_package(unstated) is False
