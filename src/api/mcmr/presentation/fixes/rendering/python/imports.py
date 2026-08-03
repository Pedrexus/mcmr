import ast
import re
from typing import TYPE_CHECKING

from .....domain.contracts import ImportRequest
from .....domain.errors import UnrenderableFix
from ...contracts import ByteEdit

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ..documents import SourceDocument


def parse_python(source: str, *, path: str) -> ast.Module:
    """Parse Python source and turn syntax failures into an autofix refusal."""
    try:
        return ast.parse(source, filename=path)
    except SyntaxError as error:
        raise UnrenderableFix(f"{path} does not parse as Python") from error


class PythonImportRenderer:
    """Render every missing import requested for one source document."""

    def __init__(
        self,
        document: SourceDocument,
        requirements: Sequence[ImportRequest],
    ) -> None:
        self.document = document
        self.requirements = list(requirements)
        self.tree = parse_python(document.text, path=document.path)

    def render(self) -> list[ByteEdit]:
        """Return insertions satisfying every missing import request."""
        if not self.requirements:
            return []
        missing = self._missing()
        if not missing:
            return []
        runtime = [request for request in missing if not request.type_only]
        type_only = [request for request in missing if request.type_only]
        guard = self._type_checking_guard()
        if type_only and guard is None:
            checking = ImportRequest(module="typing", name="TYPE_CHECKING")
            if not self._import_satisfied(checking):
                runtime.append(checking)
        self._validate_bindings(missing)
        rendered = [self._runtime_edit(runtime)] if runtime else []
        if type_only:
            rendered.append(self._type_only_edit(type_only, guard=guard))
        return rendered

    @staticmethod
    def _aliases_match(
        aliases: Sequence[ast.alias],
        *,
        name: str,
        alias: str,
    ) -> bool:
        """Whether one import alias list provides the requested binding."""
        return any(item.name == name and (item.asname or "") == alias for item in aliases)

    @staticmethod
    def _assigned_names(targets: Sequence[ast.expr]) -> set[str]:
        """Return every name an assignment target binds."""
        return {
            held.id
            for target in targets
            for held in ast.walk(target)
            if isinstance(held, ast.Name)
        }

    @staticmethod
    def _is_docstring(statement: ast.stmt) -> bool:
        """Whether one opening statement is a module docstring."""
        return (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        )

    @classmethod
    def _statement_bindings(cls, statement: ast.stmt) -> set[str]:
        """Return names one module-level statement binds."""
        match statement:
            case ast.Import(names=aliases):
                return {alias.asname or alias.name.split(".", 1)[0] for alias in aliases}
            case ast.ImportFrom(names=aliases):
                return {alias.asname or alias.name for alias in aliases}
            case ast.FunctionDef() | ast.AsyncFunctionDef() | ast.ClassDef():
                return {statement.name}
            case ast.Assign(targets=targets):
                return cls._assigned_names(targets)
            case ast.AnnAssign(target=ast.Name(id=name)):
                return {name}
            case _:
                return set()

    def _body_import_offset(self) -> int | None:
        """Return the byte behind the opening docstring and import block, when present."""
        statements = self.tree.body
        index = int(bool(statements) and self._is_docstring(statements[0]))
        while index < len(statements) and isinstance(
            statements[index], ast.Import | ast.ImportFrom
        ):
            index += 1
        if not index:
            return None
        previous = statements[index - 1]
        end = self.document.offset(
            previous.end_lineno or previous.lineno,
            column=previous.end_col_offset or 0,
        )
        return self.document.line_bounds(end)[2]

    def _header_offset(self) -> int:
        """Return the byte behind an interpreter line or source encoding declaration."""
        offset = 0
        for line in self.document.original.splitlines(keepends=True)[:2]:
            if not line.startswith(b"#!") and not re.search(rb"coding[:=]\s*[-\w.]+", line):
                break
            offset += len(line)
        return offset

    def _import_offset(self) -> int:
        """Return where new imports belong in this document."""
        body_offset = self._body_import_offset()
        return self._header_offset() if body_offset is None else body_offset

    def _import_satisfied(self, request: ImportRequest) -> bool:
        """Whether the module already imports the exact requested binding."""
        module = request.module or None
        statements = list(self.tree.body)
        if request.type_only and (guard := self._type_checking_guard()) is not None:
            statements.extend(guard.body)
        for statement in statements:
            if (
                isinstance(statement, ast.Import)
                and not request.name
                and request.level == 0
                and self._aliases_match(statement.names, name=request.module, alias=request.alias)
            ):
                return True
            if (
                isinstance(statement, ast.ImportFrom)
                and request.name
                and statement.level == request.level
                and statement.module == module
                and self._aliases_match(statement.names, name=request.name, alias=request.alias)
            ):
                return True
        return False

    def _missing(self) -> list[ImportRequest]:
        """Return unique unsatisfied requests in stable source order."""
        return sorted(
            {request for request in self.requirements if not self._import_satisfied(request)},
            key=lambda request: request.source,
        )

    def _module_bindings(self) -> set[str]:
        """Return names bound directly in module scope."""
        return set().union(*(self._statement_bindings(item) for item in self.tree.body))

    def _runtime_edit(self, missing: Sequence[ImportRequest]) -> ByteEdit:
        """Insert ordinary imports at the module import boundary."""
        offset = self._import_offset()
        return ByteEdit(
            path=self.document.path,
            start=offset,
            end=offset,
            replacement=self._source(missing, offset=offset),
        )

    def _source(self, missing: Sequence[ImportRequest], *, offset: int) -> bytes:
        """Return the complete encoded import insertion."""
        ending = self.document.newline
        source = ending.join(request.source.encode("utf-8") for request in missing) + ending
        return source + ending if offset == 0 and self.document.original else source

    def _type_checking_guard(self) -> ast.If | None:
        """Return the top-level `TYPE_CHECKING` suite when one exists."""
        return next(
            (
                statement
                for statement in self.tree.body
                if isinstance(statement, ast.If)
                and (
                    isinstance(statement.test, ast.Name)
                    and statement.test.id == "TYPE_CHECKING"
                    or isinstance(statement.test, ast.Attribute)
                    and statement.test.attr == "TYPE_CHECKING"
                )
            ),
            None,
        )

    def _type_only_edit(
        self,
        missing: Sequence[ImportRequest],
        *,
        guard: ast.If | None,
    ) -> ByteEdit:
        """Insert type-only imports into an existing or newly declared guard."""
        ending = self.document.newline
        indented = (
            ending.join(b"    " + request.source.encode("utf-8") for request in missing) + ending
        )
        if guard is None:
            offset = self._import_offset()
            return ByteEdit(
                path=self.document.path,
                start=offset,
                end=offset,
                replacement=b"if TYPE_CHECKING:" + ending + indented + ending,
            )
        imports = [item for item in guard.body if isinstance(item, ast.Import | ast.ImportFrom)]
        held = imports[-1] if imports else guard.body[0]
        boundary = self.document.offset(
            held.end_lineno or held.lineno,
            column=held.end_col_offset or 0,
        )
        offset = (
            self.document.line_bounds(boundary)[2]
            if imports
            else self.document.line_bounds(
                self.document.offset(held.lineno, column=held.col_offset)
            )[0]
        )
        return ByteEdit(
            path=self.document.path,
            start=offset,
            end=offset,
            replacement=indented,
        )

    def _validate_bindings(self, missing: Sequence[ImportRequest]) -> None:
        """Refuse a request that would shadow an existing module binding."""
        bound = self._module_bindings()
        conflict = next((request for request in missing if request.binding in bound), None)
        if conflict is not None:
            raise UnrenderableFix(
                f"{self.document.path} already binds {conflict.binding!r}, so "
                f"{conflict.source!r} would shadow it"
            )
