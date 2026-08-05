import json
from functools import partial
from pathlib import Path

import anyio
import httpx
import pytest
from mcmr_datahub.provider import DataHubProvider
from mcmr_datahub.settings import DataHubSettings
from mcmr_datahub.transport.graphql import DataHubGraphQL

from mcmr.facts import (
    DataAssetFact,
    DataAssetReferenceFact,
    DataFieldReferenceFact,
    FunctionFact,
    LiteralStringExpression,
    NodeRef,
    SourceSpan,
    StringExpressionFact,
)
from mcmr.plugins import ProviderContext, RepositoryTables, fact_table


def test_datahub_graphql_projects_catalog_assets_without_mcp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One direct GraphQL response becomes typed MCMR asset evidence."""
    monkeypatch.setenv("DATAHUB_GMS_TOKEN", "secret")

    async def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url == "https://catalog.example/api/graphql"
        assert request.headers["Authorization"] == "Bearer secret"
        assert payload["operationName"] == "MCMRDataAssets"
        return httpx.Response(
            200,
            json={
                "data": {
                    "searchAcrossEntities": {
                        "total": 1,
                        "searchResults": [
                            {
                                "entity": {
                                    "urn": "urn:li:dataset:(snowflake,orders,PROD)",
                                    "properties": {"description": "Placed orders"},
                                    "ownership": {
                                        "owners": [
                                            {
                                                "owner": {
                                                    "urn": "urn:li:corpuser:pedro",
                                                    "username": "pedro",
                                                }
                                            }
                                        ]
                                    },
                                    "domain": {
                                        "domain": {
                                            "urn": "urn:li:domain:sales",
                                            "properties": {"name": "Sales"},
                                        }
                                    },
                                    "schemaMetadata": {
                                        "fields": [
                                            {
                                                "fieldPath": "order_id",
                                                "type": "NUMBER",
                                                "description": "Stable order ID",
                                            }
                                        ]
                                    },
                                }
                            }
                        ],
                    }
                },
                "extensions": {},
            },
        )

    context = ProviderContext(
        repository=Path("."),
        settings={"server": "https://catalog.example/", "max_assets": 5},
        requested={DataAssetFact},
        dependencies=RepositoryTables(),
    )

    tables = anyio.run(DataHubProvider(httpx.MockTransport(respond)).tables, context)
    row = tables[DataAssetFact].records("assets").collect().row(0, named=True)
    assert [
        row[name]
        for name in (
            "fact_id",
            "ordinal",
            "identifier",
            "description",
            "domain",
            "is_changed",
            "owners.length",
            "fields.length",
        )
    ] == [
        "datahub-assets",
        0,
        "urn:li:dataset:(snowflake,orders,PROD)",
        "Placed orders",
        "Sales",
        False,
        1,
        1,
    ]


def test_datahub_provider_returns_its_exact_registered_family(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The entry-point provider uses public settings and returns one typed table."""
    monkeypatch.setenv("DATAHUB_GMS_URL", "https://catalog.example")
    monkeypatch.setenv("DATAHUB_GMS_TOKEN", "secret")

    context = ProviderContext(
        repository=tmp_path,
        settings={"max_assets": 1},
        requested={DataAssetFact},
        dependencies=RepositoryTables(),
    )

    async def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": {"searchAcrossEntities": {"total": 0, "searchResults": []}}},
        )

    tables = anyio.run(DataHubProvider(httpx.MockTransport(respond)).tables, context)

    assert list(tables) == [DataAssetFact]
    assert tables[DataAssetFact].facts().collect().item(0, "fact_id") == "datahub-assets"
    invalid = context.model_copy(update={"requested": {FunctionFact}})
    with pytest.raises(RuntimeError, match="family it does not own"):
        anyio.run(DataHubProvider().tables, invalid)


def test_datahub_provider_resolves_literal_sql_against_catalog_schema() -> None:
    """SQL tables and columns become source-spanned catalog reference facts."""
    source_span = SourceSpan(path="query.py", start_line=4, end_column=72)
    strings = fact_table(
        StringExpressionFact,
        [
            StringExpressionFact(
                key="query.py",
                span=source_span,
                language="python",
                expressions=[
                    LiteralStringExpression(
                        node=NodeRef(id="query.py:4:string", span=source_span),
                        runtime_value=("SELECT order_id, missing FROM warehouse.analytics.orders"),
                    )
                ],
            )
        ],
    )
    dependencies = RepositoryTables()
    dependencies.add(strings)
    context = ProviderContext(
        repository=Path("."),
        settings={"server": "https://catalog.example"},
        requested={DataAssetReferenceFact, DataFieldReferenceFact},
        dependencies=dependencies,
    )

    async def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": {
                    "searchAcrossEntities": {
                        "total": 1,
                        "searchResults": [
                            {
                                "entity": {
                                    "urn": (
                                        "urn:li:dataset:(snowflake,"
                                        "tenant.warehouse.analytics.orders,PROD)"
                                    ),
                                    "properties": {
                                        "name": "orders",
                                        "qualifiedName": "tenant.warehouse.analytics.orders",
                                        "description": "Orders",
                                    },
                                    "schemaMetadata": {
                                        "fields": [
                                            {
                                                "fieldPath": "order_id",
                                                "type": "NUMBER",
                                                "description": "Order ID",
                                            }
                                        ]
                                    },
                                }
                            }
                        ],
                    }
                }
            },
        )

    tables = anyio.run(DataHubProvider(httpx.MockTransport(respond)).tables, context)
    asset = tables[DataAssetReferenceFact].records("references").collect().row(0, named=True)
    fields = tables[DataFieldReferenceFact].records("references").collect()

    assert (
        asset["asset_exists"],
        asset["source_location"],
        fields.get_column("field_name").to_list(),
        fields.get_column("field_exists").to_list(),
        fields.get_column("catalog_type").to_list(),
    ) == (
        True,
        "query.py:4",
        ["order_id", "missing"],
        [True, False],
        ["NUMBER", ""],
    )


def test_datahub_graphql_reports_protocol_and_configuration_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configuration, lifecycle, and GraphQL errors fail before rules receive evidence."""
    monkeypatch.delenv("DATAHUB_GMS_TOKEN", raising=False)
    settings = DataHubSettings(server="https://catalog.example")
    gateway = DataHubGraphQL(settings)

    with pytest.raises(RuntimeError, match="must be opened"):
        anyio.run(partial(gateway.execute, "query Q { me { urn } }", {}, "Q"))

    async def respond(request: httpx.Request) -> httpx.Response:
        assert "Authorization" not in request.headers
        return httpx.Response(200, json={"errors": [{"message": "denied"}]})

    async def execute() -> None:
        async with DataHubGraphQL(
            settings,
            transport=httpx.MockTransport(respond),
        ) as client:
            await client.execute("query Q { me { urn } }", {}, "Q")

    with pytest.raises(RuntimeError, match="GraphQL request failed"):
        anyio.run(execute)


def test_datahub_settings_require_one_explicit_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """External rules cannot start when neither configuration source names a server."""
    monkeypatch.delenv("DATAHUB_GMS_URL", raising=False)

    with pytest.raises(ValueError, match="DataHub external rules require"):
        DataHubSettings.from_mapping({})


def test_the_catalog_is_read_in_pages_up_to_the_configured_bound() -> None:
    """Paging stops at the requested bound, and only the requested reference family is built."""
    pages: list[int] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        start = payload["variables"]["start"]
        pages.append(start)
        return httpx.Response(
            200,
            json={
                "data": {
                    "searchAcrossEntities": {
                        "total": 9,
                        "searchResults": [
                            {
                                "entity": {
                                    "urn": f"urn:li:dataset:(snowflake,page{start},PROD)",
                                    "schemaMetadata": {"fields": []},
                                }
                            }
                        ],
                    }
                }
            },
        )

    strings = fact_table(StringExpressionFact, [])
    dependencies = RepositoryTables()
    dependencies.add(strings)
    context = ProviderContext(
        repository=Path("."),
        settings={"server": "https://catalog.example", "page_size": 1, "max_assets": 2},
        requested={DataAssetReferenceFact},
        dependencies=dependencies,
    )

    tables = anyio.run(DataHubProvider(httpx.MockTransport(respond)).tables, context)

    assert (pages, list(tables)) == ([0, 1], [DataAssetReferenceFact])
