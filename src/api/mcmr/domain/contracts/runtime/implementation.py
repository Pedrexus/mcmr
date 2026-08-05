import inspect
import re
from collections.abc import Callable
from functools import cached_property
from typing import TYPE_CHECKING, Annotated, get_args, get_origin, get_type_hints

from patos import FrozenModel, Runtime
from pydantic import TypeAdapter

from ....facts import Fact
from ....table import RepositoryTables
from ...policy import Boolean, Numeric, RulePolicy
from ...primitives import NonEmptyStr, RuleSetting
from ...primitives.scope import RuleScope
from ..primitives import FixSafety
from .annotations import RuleId, output_contract, query_kind, table_type
from .interfaces.callable import invoke_table_rule

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ....execution.queries.model import ModelQuery
    from ....query import RuleQuery
    from ....table import Table
    from .interfaces import Function
    from .interfaces.dependency import RuleDependency


class Rule[**P, Result](FrozenModel):
    """Keep one table rule callable and its source identity."""

    id: RuleId
    function: Runtime[Callable[P, Result]]
    module: str
    qualname: str
    query_fix_safety: FixSafety | None = None
    policy: RulePolicy | None = None

    @property
    def callable_path(self) -> str:
        """Return the source-derived callable identity."""
        return f"{self.module}.{self.qualname}"

    @cached_property
    def hints(self) -> dict[str, type]:
        """Return evaluated annotations including numeric result metadata."""
        return get_type_hints(self.function, include_extras=True)

    @cached_property
    def injected(self) -> list[tuple[str, type]]:
        """Return every required service input that is not a repository table."""
        return [
            (parameter.name, self.hints[parameter.name])
            for parameter in self.signature.parameters.values()
            if parameter.default is inspect.Parameter.empty
            and table_type(self.hints[parameter.name]) is None
        ]

    @cached_property
    def instructions(self) -> NonEmptyStr:
        """Return the documented Definition as the model's single runtime rubric."""
        match = re.search(
            r"(?ms)^Definition\n-+\n(?P<definition>.*?)(?=^[A-Z][^\n]*\n-+\n|\Z)",
            self.raw_documentation,
        )
        if match is None:
            raise ValueError("Rule documentation needs a Definition section")
        return TypeAdapter(NonEmptyStr).validate_python(match.group("definition"))

    @cached_property
    def model_native(self) -> bool:
        """Whether this table rule returns one deferred contextual model query."""
        return query_kind(self.hints["return"]) == "ModelQuery"

    @property
    def primary_family(self) -> type[Fact]:
        """Return the table family whose rows carry this rule's output identities."""
        try:
            return self.tables[0][1]
        except IndexError as error:
            raise TypeError(f"{self.callable_path} has no table dependency") from error

    @cached_property
    def query_native(self) -> bool:
        """Whether this rule returns exactly one supported relational query."""
        return query_kind(self.hints["return"]) is not None

    @property
    def raw_documentation(self) -> str:
        """Return the complete source docstring without changing its sections."""
        return inspect.getdoc(self.function) or ""

    @cached_property
    def signature(self) -> inspect.Signature:
        """Return the source signature used for injection and settings."""
        return inspect.signature(self.function)

    @cached_property
    def table_languages(self) -> dict[str, set[str]]:
        """Return language constraints carried by annotated table dependencies."""
        languages: dict[str, set[str]] = {}
        for parameter in self.signature.parameters.values():
            annotation = self.hints[parameter.name]
            if table_type(annotation) is None:
                continue
            metadata = get_args(annotation)[1:] if get_origin(annotation) is Annotated else ()
            languages[parameter.name] = {
                str(item) for item in metadata if isinstance(item, RuleScope)
            }
        return languages

    @cached_property
    def table_native(self) -> bool:
        """Whether this rule declares at least one typed repository table."""
        return bool(self.tables)

    @cached_property
    def tables(self) -> list[tuple[str, type[Fact]]]:
        """Return every table dependency in source parameter order."""
        dependencies: list[tuple[str, type[Fact]]] = []
        for parameter in self.signature.parameters.values():
            family = table_type(self.hints[parameter.name])
            if family is not None:
                dependencies.append((parameter.name, family))
        return dependencies

    def invoke(
        self,
        tables: RepositoryTables,
        *,
        settings: Mapping[str, RuleSetting],
        dependencies: Mapping[type, RuleDependency],
        languages: Mapping[str, set[str]] | None = None,
    ) -> RuleQuery | ModelQuery:
        """Call one rule once with every annotation-declared table and service."""
        if not self.table_native:
            raise TypeError(f"{self.callable_path} is not a table rule")
        arguments: dict[str, RuleDependency | RuleSetting] = {
            name: dependencies[hint] for name, hint in self.injected
        }
        selected_languages = self.table_languages if languages is None else languages
        arguments.update(
            {
                name: tables[family].restricted(selected_languages.get(name, set()))
                for name, family in self.tables
            }
        )
        arguments.update(settings)
        return invoke_table_rule(self.function, arguments)

    def invoke_table[Family: Fact](
        self,
        subject: Table[Family],
        *,
        settings: Mapping[str, RuleSetting],
        dependencies: Mapping[type, RuleDependency],
    ) -> RuleQuery | ModelQuery:
        """Invoke a one-table rule directly for focused tests and interactive use."""
        if not self.table_native:
            raise TypeError(f"{self.callable_path} is not a table rule")
        required = {family for _, family in self.tables}
        if required != {subject.family}:
            names = ", ".join(sorted(family.__name__ for family in required))
            raise TypeError(f"{self.callable_path} requires tables {names}")
        return self.invoke(
            RepositoryTables({subject.family: subject}),
            settings=settings,
            dependencies=dependencies,
        )


def rule[**P, Result](
    identifier: RuleId,
    *,
    fix_safety: FixSafety | None = None,
    policy: RulePolicy | None = None,
) -> Callable[[Function[P, Result]], Rule[P, Result]]:
    """Wrap one typed rule function with a stable, source-validated identity."""

    def wrap(candidate: Function[P, Result]) -> Rule[P, Result]:
        output, _, _ = output_contract(get_type_hints(candidate, include_extras=True)["return"])
        owned_policy = policy
        if owned_policy is None and output == "bool":
            owned_policy = Boolean()
        elif owned_policy is None and output == "int":
            owned_policy = Numeric(maximum=0)
        return Rule(
            id=identifier,
            function=candidate,
            module=candidate.__module__,
            qualname=candidate.__qualname__,
            query_fix_safety=fix_safety,
            policy=owned_policy,
        )

    return wrap
