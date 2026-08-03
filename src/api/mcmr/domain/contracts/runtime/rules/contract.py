from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import inspect
    from collections.abc import Mapping

    from .....execution.queries.model import ModelQuery
    from .....facts import Fact
    from .....query import RuleQuery
    from .....table import Table
    from ....policy import RulePolicy
    from ....primitives import NonEmptyStr, RuleSetting
    from ...annotations import RuleId
    from ...primitives import FixSafety
    from ..interfaces.dependency import RuleDependency


class RuleContract(Protocol):
    """Expose runtime rule metadata without erasing typed call signatures."""

    @property
    def callable_path(self) -> str: ...

    @property
    def hints(self) -> dict[str, type]: ...

    @property
    def id(self) -> RuleId: ...

    @property
    def injected(self) -> list[tuple[str, type]]: ...

    @property
    def instructions(self) -> NonEmptyStr: ...

    @property
    def model_native(self) -> bool: ...

    @property
    def module(self) -> str: ...

    @property
    def policy(self) -> RulePolicy | None: ...

    @property
    def primary_family(self) -> type[Fact]: ...

    @property
    def qualname(self) -> str: ...

    @property
    def query_fix_safety(self) -> FixSafety | None: ...

    @property
    def query_native(self) -> bool: ...

    @property
    def raw_documentation(self) -> str: ...

    @property
    def signature(self) -> inspect.Signature: ...

    @property
    def table_languages(self) -> dict[str, set[str]]: ...

    @property
    def table_native(self) -> bool: ...

    @property
    def tables(self) -> list[tuple[str, type[Fact]]]: ...

    def invoke(
        self,
        tables: Mapping[type[Fact], Table[Fact]],
        *,
        settings: Mapping[str, RuleSetting],
        dependencies: Mapping[type, RuleDependency],
        languages: Mapping[str, set[str]] | None = None,
    ) -> RuleQuery | ModelQuery: ...

    def invoke_table[Family: Fact](
        self,
        subject: Table[Family],
        *,
        settings: Mapping[str, RuleSetting],
        dependencies: Mapping[type, RuleDependency],
    ) -> RuleQuery | ModelQuery: ...
