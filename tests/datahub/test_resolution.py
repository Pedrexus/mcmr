from functools import partial

import anyio
import httpx
import pytest
from mcmr_datahub.resolution.catalog import DataHubCatalog
from mcmr_datahub.resolution.references import SQLReferenceExtractor
from mcmr_datahub.settings import DataHubSettings
from mcmr_datahub.transport.graphql import DataHubGraphQL

from mcmr.facts import (
    DataAsset,
    DataField,
    LiteralStringExpression,
    NodeRef,
    SourceSpan,
    StringExpressionFact,
)
from mcmr.plugins import Table, fact_table

_SPAN = SourceSpan(path="query.py", start_line=1, start_column=0, end_column=40)


def urn(name: str) -> str:
    """Return one canonical DataHub dataset URN for a qualified warehouse name."""
    return f"urn:li:dataset:(urn:li:dataPlatform:snowflake,{name},PROD)"


def literals(*texts: str) -> Table[StringExpressionFact]:
    """Return one syntax table holding each given string literal as its own fact."""
    return fact_table(
        StringExpressionFact,
        [
            StringExpressionFact(
                key=f"query.py:{ordinal}",
                span=_SPAN,
                language="python",
                expressions=[
                    LiteralStringExpression(
                        node=NodeRef(
                            id=f"query.py:{ordinal}:string",
                            span=_SPAN,
                            kind="string",
                            text=f'"{text}"',
                        ),
                        runtime_value=text,
                    )
                ],
            )
            for ordinal, text in enumerate(texts)
        ],
    )


def resolved(catalog: DataHubCatalog, *texts: str) -> tuple[list[str], list[str]]:
    """Return the asset identifiers and field names one extractor read from the given literals."""
    assets, fields = SQLReferenceExtractor(catalog=catalog).facts(literals(*texts))
    return (
        [reference.asset_identifier for fact in assets for reference in fact.references],
        [reference.field_name for fact in fields for reference in fact.references],
    )


def test_a_name_resolves_exactly_first_and_folds_case_only_when_it_stays_unique() -> None:
    """Case folding is a fallback, and it never turns two catalog spellings into one answer."""
    catalog = DataHubCatalog(
        assets=[
            DataAsset(
                identifier=urn("Warehouse.Orders"),
                fields=[DataField(name="id", data_type="NUMBER")],
            ),
            DataAsset(identifier="plain_name"),
        ]
    )

    assert (
        resolved(catalog, "SELECT id FROM Warehouse.orders"),
        catalog.urn_name("plain_name"),
        catalog.aliases(DataAsset(identifier="plain_name")),
        catalog.resolve("nothing.here"),
    ) == (([urn("Warehouse.Orders")], ["id"]), "", {"plain_name"}, None)


def test_a_literal_states_a_urn_a_broken_query_or_nothing_at_all() -> None:
    """Only exact evidence becomes a reference, so unparsable and empty text report nothing."""
    catalog = DataHubCatalog(assets=[DataAsset(identifier=urn("warehouse.orders"))])

    assert (
        resolved(catalog, urn("warehouse.orders")),
        resolved(catalog, "SELECT FROM WHERE ((("),
        resolved(catalog, ";"),
        resolved(catalog, "hello world"),
    ) == (
        ([urn("warehouse.orders")], []),
        ([], []),
        ([], []),
        ([], []),
    )


def test_an_unqualified_column_over_two_tables_resolves_to_neither() -> None:
    """A join gives a bare column two possible owners, and guessing one would invent evidence."""
    catalog = DataHubCatalog(
        assets=[
            DataAsset(
                identifier=urn("warehouse.orders"),
                fields=[DataField(name="id", data_type="NUMBER")],
            ),
            DataAsset(
                identifier=urn("warehouse.invoices"),
                fields=[DataField(name="id", data_type="NUMBER")],
            ),
        ]
    )

    identifiers, fields = resolved(
        catalog,
        "SELECT id FROM warehouse.orders JOIN warehouse.invoices ON true",
    )

    assert (sorted(identifiers), fields) == (
        [urn("warehouse.invoices"), urn("warehouse.orders")],
        [],
    )


def test_a_rewrite_is_offered_only_for_a_column_the_literal_spells_once() -> None:
    """Two sites in one string would make the edit ambiguous, so no patch is offered."""
    catalog = DataHubCatalog(
        assets=[
            DataAsset(
                identifier=urn("warehouse.orders"),
                fields=[DataField(name="total", data_type="NUMBER")],
            )
        ]
    )
    extractor = SQLReferenceExtractor(
        catalog=catalog,
        renames={urn("warehouse.orders"): {"legacy_total": "total"}},
    )
    _assets, once = extractor.facts(literals("SELECT legacy_total FROM warehouse.orders"))
    _again, twice = extractor.facts(
        literals("SELECT legacy_total, legacy_total FROM warehouse.orders")
    )

    assert (
        once[0].references[0].repair.replacement,
        {reference.repair.replacement for reference in twice[0].references},
    ) == ('"SELECT total FROM warehouse.orders"', {""})


def test_a_response_that_omits_its_data_fails_before_a_rule_reads_it() -> None:
    """An envelope with neither data nor errors is a protocol failure, not an empty answer."""
    settings = DataHubSettings(server="https://catalog.example")

    async def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"extensions": {}})

    async def execute() -> None:
        async with DataHubGraphQL(settings, transport=httpx.MockTransport(respond)) as client:
            await client.execute("query Q { me { urn } }", {}, "Q")

    with pytest.raises(RuntimeError, match="omitted data"):
        anyio.run(execute)
    closed = DataHubGraphQL(settings)
    anyio.run(partial(closed.__aexit__, None, None, None))

    assert closed.client is None


def test_a_stated_cast_is_normalized_against_the_catalog_before_it_is_judged() -> None:
    """Only a real type disagreement survives, since `NUMBER` and `DECIMAL` name one type."""
    catalog = DataHubCatalog(
        assets=[
            DataAsset(
                identifier=urn("warehouse.orders"),
                fields=[
                    DataField(name="total", data_type="NUMBER"),
                    DataField(name="payload", data_type="RECORD"),
                ],
            )
        ]
    )
    extractor = SQLReferenceExtractor(catalog=catalog)

    def expected(text: str) -> list[str]:
        """Return the expectation the extractor retained for each column of one literal."""
        _assets, fields = extractor.facts(literals(text))
        return [reference.expected_type for reference in fields[0].references]

    assert (
        expected("SELECT CAST(total AS NUMBER) FROM warehouse.orders"),
        expected("SELECT CAST(total AS STRING) FROM warehouse.orders"),
        expected("SELECT CAST(payload AS RECORD) FROM warehouse.orders"),
        expected("SELECT total, CAST(1 AS STRING) FROM warehouse.orders"),
        expected("SELECT CAST(total AS STRING), CAST(total AS DATE) FROM warehouse.orders"),
    ) == (["NUMBER"], ["TEXT"], ["RECORD"], [""], ["", ""])
