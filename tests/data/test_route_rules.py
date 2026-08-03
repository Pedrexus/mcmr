from typing import TYPE_CHECKING

from mcmr.facts import Route, RouteFact, RouteReference, SourceSpan
from mcmr.rules.general import (
    duplicate_route_declaration,
    inconsistent_route_path_style,
    unreached_declared_route,
)

from ..support import query_value, retained_query

if TYPE_CHECKING:
    from typing import Literal


def route(
    path: str,
    *,
    method: str = "get",
    form: Literal["plain", "named", "mounted"] = "plain",
) -> Route:
    """Build one declared route and whatever names its path."""
    return Route(
        method=method,
        path=path,
        framework="decorator",
        declared_in=f"api{path.replace('/', '_')}.py",
        is_prefix_composed=form == "mounted",
        references=(
            [RouteReference(path="web/client.ts", language="typescript")]
            if form == "named"
            else []
        ),
    )


def declared(*routes: Route) -> RouteFact:
    """Build the one fact carrying every route a repository declares."""
    return RouteFact(key="routes", span=SourceSpan(path=""), routes=list(routes))


def test_route_and_reference_locate_the_source_they_retain() -> None:
    reference = RouteReference(path="web/client.ts", language="typescript", line=12)
    declaration = route("/users").model_copy(update={"line": 7})

    assert reference.span == SourceSpan(path="web/client.ts", start_line=12)
    assert declaration.span == SourceSpan(path="api_users.py", start_line=7)


def test_one_method_and_path_declared_twice_is_reported_once() -> None:
    """Only one of them serves a request and registration order decides which."""
    query = retained_query(declared(route("/users"), route("/users")), duplicate_route_declaration)
    assert query_value(query) == 1
    assert query.findings is not None
    finding = query.findings.rows.collect().row(0, named=True)
    assert finding["path"] == "api_users.py"
    assert finding["start_line"] == 1
    assert "`get /users` is declared 2 times" in finding["message"]
    assert (
        query_value(
            retained_query(
                declared(route("/users"), route("/orders")), duplicate_route_declaration
            )
        )
        == 0
    )
    assert (
        query_value(
            retained_query(
                declared(route("/users"), route("/users", method="post")),
                duplicate_route_declaration,
            )
        )
        == 0
    )


def test_a_mounted_router_is_not_judged_for_a_duplicate_it_may_not_have() -> None:
    """Its declared path is a suffix, so two routers can state the same one honestly."""
    mounted = declared(route("/users", form="mounted"), route("/users", form="mounted"))

    assert query_value(retained_query(mounted, duplicate_route_declaration)) == 0


def test_an_unreached_route_is_only_reported_where_something_reaches_another() -> None:
    """A repository whose clients live elsewhere would otherwise report every route it has."""
    query = retained_query(
        declared(route("/a", form="named"), route("/b")), unreached_declared_route
    )
    assert query_value(query) == 1
    assert query.findings is not None
    finding = query.findings.rows.collect().row(0, named=True)
    assert finding["path"] == "api_b.py"
    assert finding["start_line"] == 1
    assert "`get /b` is declared here" in finding["message"]
    assert (
        query_value(retained_query(declared(route("/a"), route("/b")), unreached_declared_route))
        == 0
    )
    assert (
        query_value(retained_query(declared(route("/a", form="named")), unreached_declared_route))
        == 0
    )


def test_a_parameterized_route_is_skipped_because_no_literal_can_match_it() -> None:
    """`/users/{id}` and `/users/7` are different strings and mean the same route."""
    facts = declared(route("/a", form="named"), route("/users/{id}"))

    assert query_value(retained_query(facts, unreached_declared_route)) == 0


def test_a_separator_is_only_wrong_where_the_repository_already_chose_one() -> None:
    """A repository with one convention has a minority; one with none has nothing to break."""
    query = retained_query(
        declared(route("/user-profiles"), route("/order-items"), route("/audit_log")),
        inconsistent_route_path_style,
    )
    assert query_value(query) == 1
    assert query.findings is not None
    finding = query.findings.rows.collect().row(0, named=True)
    assert finding["path"] == "api_audit_log.py"
    assert finding["start_line"] == 1
    assert "route convention uses `-`" in finding["message"]
    assert (
        query_value(
            retained_query(
                declared(route("/user-profiles"), route("/audit_log")),
                inconsistent_route_path_style,
            )
        )
        == 0
    )
    assert (
        query_value(
            retained_query(
                declared(route("/user-profiles"), route("/orders")),
                inconsistent_route_path_style,
            )
        )
        == 0
    )
    assert (
        query_value(
            retained_query(declared(route("/users/{user_id}")), inconsistent_route_path_style)
        )
        == 0
    )
