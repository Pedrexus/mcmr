from patos import FrozenModel

from ...foundation import Fact, NodeRef
from .expression import Expression


class CallFact(Fact):
    """Describe one resolved callable invocation."""

    class SiteIdentity(FrozenModel):
        """Retain one call's identity, inputs, receiver, and assignment."""

        qualified_name: str
        path: str
        arguments: list[Expression] = []
        keyword_names: list[str] = []
        receiver: Expression | None = None
        assigned_target: str = ""

    class SiteResolution(SiteIdentity):
        """Retain the source and resolution state for one call."""

        result_is_discarded: bool = False
        node: NodeRef
        callee: NodeRef | None = None
        is_external: bool = False
        is_standard_library: bool = False
        is_first_party: bool = False

    class SiteBehavior(SiteResolution):
        """Retain construction, alias, decorator, and async call behavior."""

        is_constructor: bool = False
        is_shadowed: bool = False
        has_ambiguous_alias: bool = False
        is_decorator_factory: bool = False
        has_starred_arguments: bool = False
        enclosing_is_async: bool = False

    class Site(SiteBehavior):
        """Retain one resolved call and its shared source facts."""

    calls: list[Site] = []
    module_bindings: list[str] = []
    is_test: bool = False
