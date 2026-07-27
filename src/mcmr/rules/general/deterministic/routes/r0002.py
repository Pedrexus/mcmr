from ..... import rule
from .....facts import RouteFact
from .....models import Count


@rule
def unreached_declared_route(subject: RouteFact) -> Count:
    """Count routes no client in this repository names, where other routes are named.

    Definition
    ----------
    Report a declared route whose path no other file states as a literal, but only in a repository
    where some declared route is named that way. A route nobody calls is either a surface someone
    forgot to remove or a contract someone forgot to wire, and both cost the reader the same
    afternoon deciding which one it is. The guard matters more than the rule, because a repository
    holding only a server has its clients elsewhere, and every route in it would read as unreached.

    Evidence
    --------
    Each finding names the method, the path, and where it is declared. The value is the number of
    unreached routes.

    Exceptions
    ----------
    A route a mounted router composes a prefix onto is skipped, since the path a client states is
    not the path the declaration states. A parameterized route is skipped for the same reason,
    because `/users/{id}` and `/users/7` are different strings and no literal match can prove they
    are the same route. A public API is legitimately unreached from inside its own repository, and
    a project that publishes one turns this rule off rather than deleting its surface.

    Examples
    --------
    In a repository whose frontend calls `"/api/users"` and `"/api/orders"`, a declared
    `"/api/legacy"` that nothing names returns `1`. In a repository with no client at all, every
    route returns `0`, because there is nothing to conclude from silence.

    References
    ----------
    Cites "Vulture documentation", dead code detection and its stated confidence limits
    https://github.com/jendrikseipp/vulture
    Cites "Refactoring", remove dead code
    Cites "OpenAPI Specification", paths and operations
    https://spec.openapis.org/oas/latest.html#paths-object
    """
    judged = [
        route for route in subject.routes if not route.is_prefix_composed and "{" not in route.path
    ]
    if not any(route.references for route in judged):
        return 0
    return sum(not route.references for route in judged)
