from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from mcmr.domain.contracts import (
    Edit,
    FixPlan,
    ImportRequest,
    Inline,
    Move,
    Placement,
    Remove,
    Rename,
    Replace,
    Unwrap,
)
from mcmr.domain.errors import UnrenderableFix
from mcmr.facts import NodeRef, SourceSpan, SymbolRef
from mcmr.presentation import PythonFixRenderer
from mcmr.presentation.fixes import (
    SourceDocument,
)
from mcmr.presentation.reports import RuleFailure

if TYPE_CHECKING:
    from pathlib import Path


def node(
    path: str,
    *,
    text: str,
    start_line: int,
    start_column: int,
    end_line: int | None = None,
    end_column: int | None = None,
    kind: str = "expression",
) -> NodeRef:
    """Address exact source through the UTF-8 byte columns providers emit."""
    return NodeRef(
        id=f"{path}:{start_line}:{start_column}:{kind}",
        span=SourceSpan(
            path=path,
            start_line=start_line,
            start_column=start_column,
            end_line=end_line or start_line,
            end_column=end_column if end_column is not None else start_column + len(text.encode()),
        ),
        kind=kind,
        text=text,
    )


def failure() -> RuleFailure:
    """Return the rule identity a rendered plan retains for verification."""
    return RuleFailure(
        rule="PY-DEMO0001",
        callable="mcmr.rules.python.deterministic.demo.r0001.demo",
        summary="Demonstrate a fix.",
        where="module:sample.py",
        span=SourceSpan(path="sample.py"),
        value=1,
        allowed="0",
    )


def render(root: Path, *rewrites: Remove | Replace | Move | Unwrap | Rename | Inline) -> str:
    """Render one plan and return the changed sample source."""
    edited = Edit(plan=FixPlan(summary="Repair the sample.", rewrites=list(rewrites)))
    fixed = PythonFixRenderer(root).render(failure(), edited, "sample needs repair")
    return fixed.files[0].revised.decode()


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"module": "enum..helpers"}, "dotted Python identifier"),
        ({"module": ""}, "dotted Python identifier"),
        ({"module": "enum", "level": 1}, "relative modules require a from import"),
        ({"module": "enum", "name": "not a name"}, "imported name"),
        ({"module": "enum", "alias": "class"}, "import alias"),
    ],
)
def test_import_requests_reject_unparseable_names(
    fields: dict[str, str],
    message: str,
) -> None:
    """An import requirement is valid Python before a renderer can receive it."""
    with pytest.raises(ValidationError, match=message):
        ImportRequest(**fields)


def test_replacement_uses_utf8_byte_columns_and_renders_a_diff(tmp_path: Path) -> None:
    """A non-ASCII character before or inside a target cannot move its byte edit."""
    source = 'label = "café"\n'
    (tmp_path / "sample.py").write_text(source)
    target = node("sample.py", text='"café"', start_line=1, start_column=8)
    edit = Edit(
        plan=FixPlan(
            summary="Use the English label.",
            rewrites=[Replace(target=target, source='"tea"')],
        )
    )

    fixed = PythonFixRenderer(tmp_path).render(failure(), edit, "label is localized")

    assert fixed.files[0].revised == b'label = "tea"\n'
    assert '-label = "caf\u00e9"' in fixed.diff
    assert '+label = "tea"' in fixed.diff


def test_replacement_adds_a_declared_import_after_the_existing_import_block(
    tmp_path: Path,
) -> None:
    """Source introduced by a fix carries its binding instead of assuming one exists."""
    source = 'from enum import StrEnum\n\nclass Mode(StrEnum):\n    FAST = "fast"\n'
    (tmp_path / "sample.py").write_text(source)
    value = node("sample.py", text='"fast"', start_line=4, start_column=11)

    revised = render(
        tmp_path,
        Replace(
            target=value,
            source="auto()",
            imports=(ImportRequest(module="enum", name="auto"),),
        ),
    )

    assert revised == (
        """from enum import StrEnum
from enum import auto

class Mode(StrEnum):
    FAST = auto()
"""
    )


def test_import_management_refuses_to_shadow_a_module_binding(tmp_path: Path) -> None:
    """Adding an import is unsafe when its local name already means something else."""
    source = "inspect = adapter\nresult = asyncio.iscoroutinefunction(callback)\n"
    (tmp_path / "sample.py").write_text(source)
    callee = node("sample.py", text="asyncio.iscoroutinefunction", start_line=2, start_column=9)

    with pytest.raises(UnrenderableFix, match="already binds 'inspect'"):
        render(
            tmp_path,
            Replace(
                target=callee,
                source="inspect.iscoroutinefunction",
                imports=(ImportRequest(module="inspect"),),
            ),
        )


def test_remove_and_unwrap_preserve_surrounding_source(tmp_path: Path) -> None:
    """Whole statements own their line ending while descendants retain their exact text."""
    source = "import os\n\nready = bool(value is None)\n"
    (tmp_path / "sample.py").write_text(source)
    imported = node("sample.py", text="import os", start_line=1, start_column=0, kind="import")
    call = node("sample.py", text="bool(value is None)", start_line=3, start_column=8, kind="call")
    operand = node("sample.py", text="value is None", start_line=3, start_column=13)

    revised = render(tmp_path, Remove(target=imported), Unwrap(target=call, keep=operand))

    assert revised == "ready = value is None\n"


@pytest.mark.parametrize(
    ("source", "line", "column", "expected"),
    [
        ('__all__ = ["Old", "Kept"]\n', 1, 11, '__all__ = ["Kept"]\n'),
        ('__all__ = ["Kept", "Old"]\n', 1, 19, '__all__ = ["Kept"]\n'),
        ('__all__ = ["Old"]\n', 1, 11, "__all__ = []\n"),
        (
            '__all__ = [\n    "Old",\n    "Kept",\n]\n',
            2,
            4,
            '__all__ = [\n    "Kept",\n]\n',
        ),
        (
            '__all__ = [\n    "Old", "Kept",\n]\n',
            2,
            4,
            '__all__ = [\n    "Kept",\n]\n',
        ),
    ],
)
def test_remove_sequence_item_owns_one_adjacent_comma(
    tmp_path: Path,
    source: str,
    *,
    line: int,
    column: int,
    expected: str,
) -> None:
    """Removing an exact export string leaves its surrounding list valid."""
    (tmp_path / "sample.py").write_text(source)
    target = node(
        "sample.py",
        text='"Old"',
        start_line=line,
        start_column=column,
        kind="sequence-item",
    )

    assert render(tmp_path, Remove(target=target)) == expected


def test_remove_sequence_item_consumes_spacing_before_its_comma(tmp_path: Path) -> None:
    """A formatter may leave space between an addressed string and its comma."""
    (tmp_path / "sample.py").write_text('__all__ = ["Old"  , "Kept"]\n')
    target = node(
        "sample.py",
        text='"Old"',
        start_line=1,
        start_column=11,
        kind="sequence-item",
    )

    assert render(tmp_path, Remove(target=target)) == '__all__ = ["Kept"]\n'


def test_remove_grouped_import_binding_preserves_live_siblings(tmp_path: Path) -> None:
    """The shared sequence deletion also owns one imported alias and its comma."""
    (tmp_path / "sample.py").write_text("from package import Old, Kept\n")
    target = node(
        "sample.py",
        text="Old",
        start_line=1,
        start_column=20,
        kind="sequence-item",
    )

    assert render(tmp_path, Remove(target=target)) == "from package import Kept\n"


def test_move_reindents_a_statement_out_of_a_try_block(tmp_path: Path) -> None:
    """A moved statement adopts its anchor's indentation and leaves the suite parseable."""
    source = """def load(stream):
    try:
        mode = "rb"
        return stream.read()
    except OSError:
        return b""
"""
    (tmp_path / "sample.py").write_text(source)
    target = node("sample.py", text='mode = "rb"', start_line=3, start_column=8, kind="statement")
    anchor_text = '''try:
        mode = "rb"
        return stream.read()
    except OSError:
        return b""'''
    anchor = node(
        "sample.py",
        text=anchor_text,
        start_line=2,
        start_column=4,
        end_line=6,
        end_column=18,
        kind="try",
    )

    revised = render(tmp_path, Move(target=target, anchor=anchor, placement=Placement.BEFORE))

    assert revised == (
        """def load(stream):
    mode = "rb"
    try:
        return stream.read()
    except OSError:
        return b""
"""
    )


def test_move_preserves_method_separation(tmp_path: Path) -> None:
    """A reordered method keeps one blank line before its new neighbor."""
    source = (
        "class Service:\n    def zeta(self):\n        pass\n\n    def alpha(self):\n        pass\n"
    )
    (tmp_path / "sample.py").write_text(source)
    target = node(
        "sample.py",
        text="def alpha(self):\n        pass",
        start_line=5,
        start_column=4,
        end_line=6,
        end_column=12,
        kind="method",
    )
    anchor = node(
        "sample.py",
        text="def zeta(self):\n        pass",
        start_line=2,
        start_column=4,
        end_line=3,
        end_column=12,
        kind="method",
    )
    deletion = SourceDocument(tmp_path, "sample.py").deletion_range(anchor)
    assert source.encode()[slice(*deletion)] == b"    def zeta(self):\n        pass\n\n"

    revised = render(tmp_path, Move(target=target, anchor=anchor, placement=Placement.BEFORE))

    assert revised == (
        "class Service:\n    def alpha(self):\n        pass\n\n    def zeta(self):\n        pass\n"
    )


def test_move_can_add_destination_owned_python_syntax(tmp_path: Path) -> None:
    """A review move may add a decorator required by its new owner."""
    source = """def helper(value):
    return value


class Service:
    def run(self):
        pass
"""
    (tmp_path / "sample.py").write_text(source)
    helper = node(
        "sample.py",
        text="def helper(value):\n    return value",
        start_line=1,
        start_column=0,
        end_line=2,
        end_column=16,
        kind="function",
    )
    method = node(
        "sample.py",
        text="def run(self):\n        pass",
        start_line=6,
        start_column=4,
        end_line=7,
        end_column=12,
        kind="method",
    )

    revised = render(
        tmp_path,
        Move(
            target=helper,
            anchor=method,
            placement=Placement.BEFORE,
            prefix="@staticmethod\n",
        ),
    )

    assert (
        revised
        == """class Service:
    @staticmethod
    def helper(value):
        return value

    def run(self):
        pass
"""
    )


def test_move_crosses_python_files_with_relative_and_type_only_imports(tmp_path: Path) -> None:
    """A cross-file move preserves its destination imports and removes its source declaration."""
    (tmp_path / "source.py").write_text(
        "from functools import cache\n\n"
        "@cache\n"
        "def build(value: Fact):\n"
        "    return helper(value)\n"
    )
    (tmp_path / "target.py").write_text(
        "from typing import TYPE_CHECKING\n\n"
        "if TYPE_CHECKING:\n"
        "    from package import Existing\n\n\n"
        "class Owner:\n"
        "    pass\n"
    )
    target = node(
        "source.py",
        text="@cache\ndef build(value: Fact):\n    return helper(value)",
        start_line=3,
        start_column=0,
        end_line=5,
        end_column=24,
        kind="function",
    )
    anchor = node(
        "target.py",
        text="class Owner:\n    pass",
        start_line=7,
        start_column=0,
        end_line=8,
        end_column=8,
        kind="class",
    )
    edit = Edit(
        plan=FixPlan(
            summary="Move build beside its owner.",
            rewrites=[
                Move(
                    target=target,
                    anchor=anchor,
                    placement=Placement.AFTER,
                    imports=[
                        ImportRequest(module="functools", name="cache"),
                        ImportRequest(module="helpers", name="helper", level=2),
                        ImportRequest(module="package", name="Fact", type_only=True),
                    ],
                )
            ],
        )
    )

    fixed = PythonFixRenderer(tmp_path).render(failure(), edit, "move build")
    revised = {file.path: file.revised.decode() for file in fixed.files}

    assert (
        revised["source.py"],
        "from ..helpers import helper" in revised["target.py"],
        "    from package import Fact" in revised["target.py"],
        revised["target.py"].endswith(
            "class Owner:\n    pass\n\n@cache\ndef build(value: Fact):\n    return helper(value)\n"
        ),
    ) == (
        "from functools import cache\n\n",
        True,
        True,
        True,
    )


def test_last_method_without_a_leading_blank_keeps_its_owner_line(tmp_path: Path) -> None:
    """Removing a class's only method never consumes the class declaration."""
    (tmp_path / "sample.py").write_text("class Service:\n    def run(self):\n        pass\n")
    method = node(
        "sample.py",
        text="def run(self):\n        pass",
        start_line=2,
        start_column=4,
        end_line=3,
        end_column=12,
        kind="method",
    )

    assert SourceDocument(tmp_path, "sample.py").deletion_range(method) == (15, 47)


def test_rename_requires_complete_references_and_changes_them_atomically(tmp_path: Path) -> None:
    """A symbol rename touches its declaration and every proven reference or does nothing."""
    source = "def ready():\n    return True\n\nif ready():\n    pass\n"
    (tmp_path / "sample.py").write_text(source)
    declaration = node("sample.py", text="ready", start_line=1, start_column=4, kind="name")
    reference = node("sample.py", text="ready", start_line=4, start_column=3, kind="reference")
    symbol = SymbolRef(
        id="sample.ready",
        name="ready",
        declaration=declaration,
        references=[reference],
        are_references_complete=True,
    )

    revised = render(tmp_path, Rename(symbol=symbol, name="is_ready"))

    assert revised == "def is_ready():\n    return True\n\nif is_ready():\n    pass\n"
    with pytest.raises(UnrenderableFix, match="incomplete"):
        render(
            tmp_path,
            Rename(
                symbol=symbol.model_copy(update={"are_references_complete": False}),
                name="is_ready",
            ),
        )
