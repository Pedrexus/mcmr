from mcmr.facts import Route, RouteFact, RouteReference, SourceSpan
from mcmr.rules.general.deterministic.routes.r0001 import duplicate_route_declaration
from mcmr.rules.general.deterministic.routes.r0002 import unreached_declared_route
from mcmr.rules.general.deterministic.routes.r0003 import inconsistent_route_path_style


def route(path: str, *, method: str = "get", named: bool = False, mounted: bool = False) -> Route:
    """Build one declared route and whatever names its path."""
    return Route(
        method=method,
        path=path,
        framework="decorator",
        declared_in=f"api{path.replace('/', '_')}.py",
        is_prefix_composed=mounted,
        references=[RouteReference(path="web/client.ts", language="typescript")] if named else [],
    )


def declared(*routes: Route) -> RouteFact:
    """Build the one fact carrying every route a repository declares."""
    return RouteFact(key="routes", span=SourceSpan(path=""), routes=list(routes))


def test_one_method_and_path_declared_twice_is_reported_once() -> None:
    """Only one of them serves a request and registration order decides which."""
    assert duplicate_route_declaration(declared(route("/users"), route("/users"))) == 1
    assert duplicate_route_declaration(declared(route("/users"), route("/orders"))) == 0
    assert (
        duplicate_route_declaration(declared(route("/users"), route("/users", method="post"))) == 0
    )


def test_a_mounted_router_is_not_judged_for_a_duplicate_it_may_not_have() -> None:
    """Its declared path is a suffix, so two routers can state the same one honestly."""
    mounted = declared(route("/users", mounted=True), route("/users", mounted=True))

    assert duplicate_route_declaration(mounted) == 0


def test_an_unreached_route_is_only_reported_where_something_reaches_another() -> None:
    """A repository whose clients live elsewhere would otherwise report every route it has."""
    assert unreached_declared_route(declared(route("/a", named=True), route("/b"))) == 1
    assert unreached_declared_route(declared(route("/a"), route("/b"))) == 0
    assert unreached_declared_route(declared(route("/a", named=True))) == 0


def test_a_parameterized_route_is_skipped_because_no_literal_can_match_it() -> None:
    """`/users/{id}` and `/users/7` are different strings and mean the same route."""
    facts = declared(route("/a", named=True), route("/users/{id}"))

    assert unreached_declared_route(facts) == 0


def test_a_separator_is_only_wrong_where_the_repository_already_chose_one() -> None:
    """A repository with one convention has a minority; one with none has nothing to break."""
    assert (
        inconsistent_route_path_style(declared(route("/user-profiles"), route("/audit_log"))) == 1
    )
    assert inconsistent_route_path_style(declared(route("/user-profiles"), route("/orders"))) == 0
    assert inconsistent_route_path_style(declared(route("/users/{user_id}"))) == 0
