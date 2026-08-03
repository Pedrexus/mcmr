from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from .....execution.queries.model import ModelQuery
    from .....query import RuleQuery
    from ....primitives import RuleSetting
    from .dependency import RuleDependency


class _RuntimeTableRule(Protocol):
    """Invoke one validated rule through named injected inputs."""

    def __call__(
        self,
        **inputs: RuleDependency | RuleSetting,
    ) -> RuleQuery | ModelQuery: ...


def invoke_table_rule[**P, Result](
    function: Callable[P, Result],
    inputs: Mapping[str, RuleDependency | RuleSetting],
) -> RuleQuery | ModelQuery:
    """Invoke a catalog-validated callable through its dependency mapping."""
    return cast("_RuntimeTableRule", function)(**inputs)
