from typing import TYPE_CHECKING, cast

import pytest

from mcmr.domain.contracts import RuleContract, RuleSetting, RuleValue
from mcmr.facts import (
    CommentFact,
    CommentGroup,
    ImportBindingFact,
    ModuleFact,
    NodeRef,
    SourceSpan,
    SyntaxFact,
)
from mcmr.query import RuleQuery, scalar_frame_value
from mcmr.rules.general import non_ascii_source_path, reflective_scope_read, unresolved_work_marker
from mcmr.rules.python import dynamic_super_receiver, relative_import_beyond_package
from mcmr.table import AnalysisSession, ImportBindingRelation, SyntaxRelation

from ..support import retained_query

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from mcmr.plugins import Fact, Table

_SPAN = SourceSpan(path="src/engine.py")


def query(
    table: Table[Fact],
    rule: RuleContract,
    **settings: RuleSetting,
) -> RuleQuery:
    """Invoke one specialized Pylint-gap rule once over a repository table."""
    result = rule.invoke_table(table, settings=settings, dependencies={})
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic Pylint-gap rule returned a model query")
    return result


def scalar(result: RuleQuery, fact_id: str | None = None) -> RuleValue:
    """Return one generic scalar or one selected specialized scalar."""
    values = result.values.collect()
    if fact_id is not None:
        values = values.filter(values["fact_id"] == fact_id)
    return scalar_frame_value(values)


def syntax_table(root: Path, source: str) -> Table[Fact]:
    """Parse one Python fixture into native syntax relations."""
    (root / "engine.py").write_text(source, encoding="utf-8")
    return cast(
        "Table[Fact]",
        AnalysisSession(
            root,
            suffixes=(".py",),
            typed_families=(SyntaxFact,),
        ).syntax_tables(),
    )


def syntax_id(table: Table[Fact], qualname: str) -> str:
    """Return the stable fact identity for one syntax declaration."""
    facts = table.frame(SyntaxRelation.FACTS)
    identity = facts.filter(facts["qualname"] == qualname).item(0, "fact_id")
    if not isinstance(identity, str):
        raise TypeError("a syntax row has no string identity")
    return identity


def import_table(root: Path, sources: Mapping[str, str]) -> Table[Fact]:
    """Parse one Python package fixture into native import-binding relations."""
    for name, source in sources.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    return cast(
        "Table[Fact]",
        AnalysisSession(
            root,
            suffixes=(".py",),
            typed_families=(ImportBindingFact,),
        ).import_binding_tables(),
    )


def import_value(result: RuleQuery, table: Table[Fact], path: str) -> RuleValue:
    """Return the scalar for the only import binding in one source file."""
    facts = table.frame(ImportBindingRelation.FACTS).select("fact_id", "path")
    values = result.values.collect().join(facts, on="fact_id")
    return scalar_frame_value(values.filter(values["path"] == path))


def comments(*texts: str) -> CommentFact:
    """Build one file's comment groups, each carrying the source it spans."""
    return CommentFact(
        key="comments:src/engine.py",
        span=_SPAN,
        groups=[
            CommentGroup(
                line_count=len(text.splitlines()) or 1,
                character_count=len(text),
                token_count=len(text.split()),
                node=NodeRef(id=f"comment:{index}", span=_SPAN, kind="comment", text=text),
            )
            for index, text in enumerate(texts)
        ],
    )


def test_a_marker_opening_a_comment_is_counted_in_any_language() -> None:
    """A note left in place of the work is the same unpaid debt whichever language wrote it."""
    subject = comments(
        "# TODO: handle the empty case",
        "// FIXME broken\n/* XXX later */",
    )

    answer = retained_query(subject, unresolved_work_marker)
    assert answer.findings is not None
    findings = answer.findings.rows.collect()
    assert (scalar(answer), findings.get_column("message").to_list()) == (
        3,
        [
            "`TODO` marks unresolved work in this comment group",
            "`FIXME` marks unresolved work in this comment group",
            "`XXX` marks unresolved work in this comment group",
        ],
    )
    assert dict(
        zip(
            findings.item(0, "measurement_names"),
            findings.item(0, "measurement_values"),
            strict=True,
        )
    ) == {"lines in the comment group": 1}
    assert answer.fix is None
    assert findings.get_column("choice_question").to_list() == [
        "resolve the `TODO` before removing its source marker",
        "resolve the `FIXME` before removing its source marker",
        "resolve the `XXX` before removing its source marker",
    ]
    assert findings.get_column("choice_options").to_list() == [
        ["complete the work", "track it outside the source"],
        ["complete the work", "track it outside the source"],
        ["complete the work", "track it outside the source"],
    ]
    assert scalar(retained_query(subject, unresolved_work_marker, markers=["todo"])) == 1


def test_a_marker_inside_a_sentence_is_prose_about_the_work() -> None:
    """`# rewrite the todo list` describes the code, and Pylint reads it the same way."""
    assert scalar(retained_query(comments("# rewrite the todo list"), unresolved_work_marker)) == 0
    assert scalar(retained_query(comments("# HACK: pin the version"), unresolved_work_marker)) == 1


def test_a_trailing_marker_beside_code_still_counts() -> None:
    """A group spans from the first comment to the last, so it carries the code between them."""
    subject = comments("# FIXME: encoding\n    return value  # XXX later")

    assert scalar(retained_query(subject, unresolved_work_marker)) == 2


def test_a_group_with_no_retained_source_is_not_read() -> None:
    """A group whose node the provider did not fill states no text to search."""
    subject = comments("# TODO: one").model_copy(
        update={"groups": [CommentGroup(line_count=1, character_count=1, token_count=1)]}
    )

    assert scalar(retained_query(subject, unresolved_work_marker)) == 0


def test_every_path_component_outside_ascii_is_counted() -> None:
    """An archive, a build system, and a shell each reproduce the whole path, not its last part."""
    both = ModuleFact(key="module:x", span=SourceSpan(path="src/café/lecteur_à_jour.py"))
    directory = ModuleFact(key="module:y", span=SourceSpan(path="src/café/reader.py"))

    assert scalar(retained_query(both, non_ascii_source_path)) == 2
    assert scalar(retained_query(directory, non_ascii_source_path)) == 1
    assert (
        scalar(retained_query(ModuleFact(key="module:z", span=_SPAN), non_ascii_source_path)) == 0
    )


def test_a_callable_reading_its_own_scope_is_reported(tmp_path: Path) -> None:
    """A body handing back its own scope makes every binding in it unprovable to any reader."""
    table = syntax_table(
        tmp_path,
        "def render(template):\n    scope = locals()\n    return format(template), scope\n",
    )
    default = query(table, reflective_scope_read)
    formatted = query(table, reflective_scope_read, reflections=["format"])
    disabled = query(table, reflective_scope_read, reflections=[])
    identity = syntax_id(table, "render")

    assert scalar(default, identity) == 1
    assert scalar(formatted, identity) == 1
    assert scalar(disabled, identity) == 0


def test_a_member_call_is_the_project_rather_than_the_builtin(tmp_path: Path) -> None:
    """`self.locals()` is a method somebody wrote, and it opens no scope."""
    table = syntax_table(
        tmp_path,
        "class Engine:\n    def run(self):\n        return self.locals()\n",
    )

    assert scalar(query(table, reflective_scope_read), syntax_id(table, "Engine.run")) == 0


def test_a_declaration_that_is_not_a_callable_body_is_not_judged(tmp_path: Path) -> None:
    """A type's tree stops at its methods, so a scope read inside one is not in it."""
    table = syntax_table(
        tmp_path,
        "class Engine:\n    scope = locals()\n\ndef quiet():\n    return 1\n",
    )
    result = query(table, reflective_scope_read)

    assert scalar(result, syntax_id(table, "Engine")) == 0
    assert scalar(result, syntax_id(table, "quiet")) == 0


@pytest.mark.parametrize(
    ("body", "expected"),
    (
        pytest.param(
            """        first = super(type(self), self).run()
        second = super(self.__class__, self).run()
        return first, second
""",
            2,
            id="receiver-computed",
        ),
        pytest.param(
            """        first = super(Engine, self).run()
        second = super().run()
        return first, second
""",
            0,
            id="class-explicit",
        ),
        pytest.param(
            "        held = super(type(self), self)\n        return held\n",
            0,
            id="object-only-assigned",
        ),
    ),
)
def test_dynamic_super_requires_a_receiver_computed_member_lookup(
    tmp_path: Path, body: str, expected: int
) -> None:
    """Only a member lookup through a receiver-computed `super` restarts dispatch recursively."""
    table = syntax_table(
        tmp_path,
        "class Engine:\n    def run(self):\n" + body,
    )

    assert scalar(query(table, dynamic_super_receiver), syntax_id(table, "Engine.run")) == expected


def test_a_function_outside_a_class_states_no_owner_to_compare(tmp_path: Path) -> None:
    """A bare function calling `super` is a different Pylint message about a different defect."""
    table = syntax_table(
        tmp_path,
        "def run():\n    return super().run()\n",
    )

    assert scalar(query(table, dynamic_super_receiver), syntax_id(table, "run")) == 0


def test_an_import_climbing_past_its_top_level_package_is_reported(tmp_path: Path) -> None:
    """Two dots from a module whose package has one component leaves the tree entirely."""
    table = import_table(
        tmp_path,
        {
            "pkg/beyond.py": "from ..outside import thing\n",
            "pkg/inside.py": "from .sibling import thing\n",
        },
    )
    result = query(table, relative_import_beyond_package)

    assert import_value(result, table, "pkg/beyond.py") is True
    assert import_value(result, table, "pkg/inside.py") is False


def test_a_package_initializer_affords_one_more_level_than_its_neighbours(tmp_path: Path) -> None:
    """`pkg/sub/__init__.py` is `pkg.sub` itself, where `pkg/sub/module.py` only sits in it."""
    table = import_table(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/sub/__init__.py": "from .. import thing\n",
            "pkg/sub/module.py": "from ... import thing\n",
        },
    )
    result = query(table, relative_import_beyond_package)

    assert import_value(result, table, "pkg/sub/__init__.py") is False
    assert import_value(result, table, "pkg/sub/module.py") is True


def test_a_module_in_no_package_has_no_top_level_to_exceed(tmp_path: Path) -> None:
    """The interpreter answers a script with a different failure, so this declines to judge it."""
    table = import_table(
        tmp_path,
        {
            "script.py": "from . import thing\n",
            "pkg/module.py": "import json\n",
        },
    )
    result = query(table, relative_import_beyond_package)

    assert import_value(result, table, "script.py") is False
    assert import_value(result, table, "pkg/module.py") is False
