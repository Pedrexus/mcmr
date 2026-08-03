from functools import partial
from typing import TYPE_CHECKING

import pytest

from mcmr.domain.contracts import (
    ImportRequest,
    Replace,
)
from mcmr.domain.errors import UnrenderableFix
from mcmr.facts import SourceSpan
from mcmr.presentation.fixes import (
    SourceDocument,
)

if TYPE_CHECKING:
    from pathlib import Path

from ..test_operations import node, render


def test_source_document_refuses_invalid_coordinates_and_evidence(tmp_path: Path) -> None:
    """Every provider coordinate is checked before it can become an edit."""
    (tmp_path / "broken.py").write_bytes(b"\xff")
    with pytest.raises(UnrenderableFix, match="not valid UTF-8"):
        SourceDocument(tmp_path, "broken.py")

    (tmp_path / "sample.py").write_text("value = 1\n")
    document = SourceDocument(tmp_path, "sample.py")
    cases = [
        ("no line 9", partial(document.offset, 9, column=0)),
        ("no byte column 99", partial(document.offset, 1, column=99)),
        ("was read against", partial(document.span_range, SourceSpan(path="other.py"))),
        (
            "retains no source text",
            partial(
                document.node_range,
                node("sample.py", text="", start_line=1, start_column=0),
            ),
        ),
        ("does not open after indentation", partial(document.indentation, 7)),
    ]
    for message, operation in cases:
        with pytest.raises(UnrenderableFix, match=message):
            operation()
    assert document.deletion_range(
        node("sample.py", text="value", start_line=1, start_column=0)
    ) == (0, 5)


def test_source_document_preserves_line_boundaries_and_default_ending(tmp_path: Path) -> None:
    """Line framing follows source bytes and defaults to a newline when absent."""
    (tmp_path / "sample.py").write_bytes(b"value = 1\r\nlast = 2")
    document = SourceDocument(tmp_path, "sample.py")
    assert (document.line_bounds(0), document.line_bounds(11)) == (
        (0, 9, 11),
        (11, 19, 19),
    )

    (tmp_path / "sample.py").write_bytes(b"value = 1")
    assert SourceDocument(tmp_path, "sample.py").newline == b"\n"


def test_imports_respect_headers_and_line_endings(tmp_path: Path) -> None:
    """Import insertion preserves executable headers and established line endings."""
    source = b"#!/usr/bin/env python\r\n# coding: utf-8\r\nvalue = asyncio.run(job)\r\n"
    (tmp_path / "sample.py").write_bytes(source)
    target = node("sample.py", text="asyncio.run", start_line=3, start_column=8)
    revised = render(
        tmp_path,
        Replace(
            target=target,
            source="inspect.run",
            imports=(ImportRequest(module="inspect"),),
        ),
    )
    assert revised.startswith("#!/usr/bin/env python\r\n# coding: utf-8\r\nimport inspect\r\n")


def test_imports_follow_module_docstrings(tmp_path: Path) -> None:
    """A module docstring remains before imports introduced by a repair."""
    (tmp_path / "sample.py").write_text('"""A module."""\nvalue = old\n')
    target = node("sample.py", text="old", start_line=2, start_column=8)
    revised = render(
        tmp_path,
        Replace(
            target=target,
            source="inspect",
            imports=(ImportRequest(module="inspect"),),
        ),
    )
    assert revised == '"""A module."""\nimport inspect\nvalue = inspect\n'


def test_type_only_imports_create_one_guard_with_relative_semantics(tmp_path: Path) -> None:
    """A type-only request creates its guard without turning the dependency into runtime code."""
    (tmp_path / "sample.py").write_text("value: int\n")
    target = node("sample.py", text="int", start_line=1, start_column=7)

    revised = render(
        tmp_path,
        Replace(
            target=target,
            source="Factory",
            imports=(ImportRequest(module="models", name="Factory", level=1, type_only=True),),
        ),
    )

    assert revised == (
        "from typing import TYPE_CHECKING\n\n"
        "if TYPE_CHECKING:\n"
        "    from .models import Factory\n\n"
        "value: Factory\n"
    )


def test_type_only_imports_reuse_an_existing_type_checking_binding(tmp_path: Path) -> None:
    """A missing guard reuses the module's existing TYPE_CHECKING import."""
    (tmp_path / "sample.py").write_text("from typing import TYPE_CHECKING\n\nvalue: int\n")
    target = node("sample.py", text="int", start_line=3, start_column=7)

    revised = render(
        tmp_path,
        Replace(
            target=target,
            source="Factory",
            imports=(ImportRequest(module="models", name="Factory", type_only=True),),
        ),
    )

    assert revised.count("from typing import TYPE_CHECKING") == 1
    assert "if TYPE_CHECKING:\n    from models import Factory" in revised


def test_imports_do_not_repeat_existing_bindings(tmp_path: Path) -> None:
    """An exact module or symbol import appears only once after rendering."""
    (tmp_path / "sample.py").write_text("import inspect\nfrom enum import auto\n\nvalue = old\n")
    target = node("sample.py", text="old", start_line=4, start_column=8)
    revised = render(
        tmp_path,
        Replace(
            target=target,
            source="(inspect, auto)",
            imports=(
                ImportRequest(module="inspect"),
                ImportRequest(module="enum", name="auto"),
            ),
        ),
    )
    assert revised.count("import inspect") == 1
    assert revised.count("from enum import auto") == 1


def test_first_import_is_separated_from_module_code(tmp_path: Path) -> None:
    """The first introduced import retains one blank line before module code."""
    (tmp_path / "sample.py").write_text("value = old\n")
    target = node("sample.py", text="old", start_line=1, start_column=8)
    revised = render(
        tmp_path,
        Replace(
            target=target,
            source="inspect",
            imports=(ImportRequest(module="inspect"),),
        ),
    )
    assert revised == "import inspect\n\nvalue = inspect\n"


def test_imports_follow_the_first_ending_in_a_mixed_file(tmp_path: Path) -> None:
    """Import insertion follows the source's established first line ending."""
    source = b"#!/usr/bin/env python\nvalue = asyncio.run(job)\r\n"
    (tmp_path / "sample.py").write_bytes(source)
    target = node("sample.py", text="asyncio.run", start_line=2, start_column=8)

    revised = render(
        tmp_path,
        Replace(
            target=target,
            source="inspect.run",
            imports=(ImportRequest(module="inspect"),),
        ),
    )

    assert revised.startswith("#!/usr/bin/env python\nimport inspect\n")


@pytest.mark.parametrize(
    ("declaration", "import_request"),
    [
        ("import os as operating", ImportRequest(module="operating")),
        (
            "from enum import auto as automatic",
            ImportRequest(module="automatic"),
        ),
        ("def function(): pass", ImportRequest(module="function")),
        ("async def asynchronous(): pass", ImportRequest(module="asynchronous")),
        ("class Service: pass", ImportRequest(module="Service")),
        ("first = second = 1", ImportRequest(module="first")),
        ("annotated: int", ImportRequest(module="annotated")),
    ],
    ids=("import", "from-import", "function", "async-function", "class", "assign", "annotated"),
)
def test_import_binding_index_covers_every_module_scope_declaration(
    tmp_path: Path,
    declaration: str,
    import_request: ImportRequest,
) -> None:
    """A requested import refuses every ordinary way its binding could already be owned."""
    (tmp_path / "sample.py").write_text(f"{declaration}\nvalue = old\n")
    target = node("sample.py", text="old", start_line=2, start_column=8)

    with pytest.raises(
        UnrenderableFix,
        match=f"already binds {import_request.binding!r}",
    ):
        render(
            tmp_path,
            Replace(
                target=target,
                source=import_request.binding,
                imports=(import_request,),
            ),
        )
