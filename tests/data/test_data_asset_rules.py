from typing import TYPE_CHECKING

import pytest

from mcmr import Numeric
from mcmr.domain.contracts import RuleContract, RuleSetting, RuleValue
from mcmr.facts import (
    DataAsset,
    DataAssetFact,
    DataAssetReference,
    DataAssetReferenceFact,
    DataChange,
    DataChangeFact,
    DataField,
    DataFieldReference,
    DataFieldReferenceFact,
    LineageEdge,
    LineageEdgeFact,
    SourceSpan,
)
from mcmr.plugins import Fact, RepositoryTables
from mcmr.plugins import fact_table as in_memory_table
from mcmr.query import RuleQuery, scalar_row_value
from mcmr.rules.general import (
    data_asset_governance_gap,
    data_change_test_gap_percentage,
    data_definition_gap_percentage,
    incompatible_data_field_type,
    missing_data_asset_reference,
    missing_data_field_reference,
    nonactive_data_asset_reference,
    ungoverned_data_reference,
    ungoverned_sensitive_field,
    unhealthy_data_dependency,
    unowned_high_impact_asset,
    unresolved_lineage_endpoint,
)

if TYPE_CHECKING:
    from ..support import Declared

_SPAN = SourceSpan(path="catalog")


def fact_table(*declared: Fact) -> RepositoryTables:
    """Normalize the given facts into one in-memory table for each family they name."""
    grouped: dict[type[Fact], list[Fact]] = {}
    for fact in declared:
        grouped.setdefault(type(fact), []).append(fact)
    repository = RepositoryTables()
    for family, subjects in grouped.items():
        repository.add(in_memory_table(family, subjects))
    return repository


def query(
    subject: RepositoryTables,
    rule: RuleContract,
    **settings: RuleSetting,
) -> RuleQuery:
    """Execute one deterministic rule once over the retained tables it declares."""
    result = rule.invoke(subject, settings=settings, dependencies={})
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic data asset rule returned a model query")
    return result


def values(result: RuleQuery) -> list[RuleValue]:
    """Return every scalar emitted by one table query in fact order."""
    return [scalar_row_value(row) for row in result.values.collect().iter_rows(named=True)]


def value(
    subject: RepositoryTables,
    rule: RuleContract,
    **settings: RuleSetting,
) -> RuleValue:
    """Return the one scalar emitted for a single retained fact."""
    answers = values(query(subject, rule, **settings))
    if len(answers) != 1:
        raise ValueError(f"expected one data asset value and received {len(answers)}")
    return answers[0]


def messages(subject: RepositoryTables, rule: RuleContract, **settings: RuleSetting) -> list[str]:
    """Return every precise message emitted by one deterministic data asset rule."""
    findings = query(subject, rule, **settings).findings
    return [] if findings is None else findings.rows.collect().get_column("message").to_list()


def asset_reference(location: str, *, identifier: str, **declared: Declared) -> DataAssetReference:
    """Return one reference to a data asset, carrying what the catalog resolved about it."""
    return DataAssetReference.model_validate(
        {"source_location": location, "asset_identifier": identifier} | declared
    )


def field_reference(*, identifier: str, field: str, **declared: Declared) -> DataFieldReference:
    """Return one reference to a field of a data asset, and what the catalog resolved of it."""
    named = {"asset_identifier": identifier, "field_name": field}
    return DataFieldReference.model_validate(named | declared)


def assets(*declared: DataAsset) -> DataAssetFact:
    """Return one catalog fact holding the given declared data assets."""
    return DataAssetFact(key="assets", span=_SPAN, assets=list(declared))


def test_reference_resolution_cases() -> None:
    """Each rule counts the references the catalog could not answer for, by asset and by field."""
    references = DataAssetReferenceFact(
        key="asset references",
        span=_SPAN,
        references=[
            asset_reference("a.py:1", identifier="orders", asset_exists=False),
            asset_reference(
                "b.py:1",
                identifier="users",
                asset_exists=True,
                lifecycle="deprecated",
                upstream_health={"warehouse": "unhealthy", "raw_users": "unknown"},
            ),
            asset_reference(
                "c.py:1",
                identifier="events",
                asset_exists=True,
                lifecycle="active",
                upstream_health={"collector": "healthy"},
            ),
        ],
    )
    reference_table = fact_table(references)
    assert (
        value(reference_table, missing_data_asset_reference),
        value(reference_table, nonactive_data_asset_reference),
        value(reference_table, unhealthy_data_dependency),
    ) == (1, 1, 1)

    fields = DataFieldReferenceFact(
        key="field references",
        span=_SPAN,
        references=[
            field_reference(
                identifier="missing", field="id", asset_exists=False, field_exists=False
            ),
            field_reference(
                identifier="orders",
                field="missing",
                asset_exists=True,
                field_exists=False,
            ),
            field_reference(
                identifier="orders",
                field="amount",
                asset_exists=True,
                field_exists=True,
                expected_type=" DECIMAL ",
                catalog_type="decimal",
            ),
            field_reference(
                identifier="orders",
                field="created_at",
                asset_exists=True,
                field_exists=True,
                expected_type="timestamp",
                catalog_type="string",
            ),
        ],
    )
    field_table = fact_table(fields)
    assert (
        value(field_table, missing_data_field_reference),
        value(field_table, incompatible_data_field_type),
        messages(field_table, missing_data_field_reference),
    ) == (
        1,
        1,
        ["field `orders.missing` is absent from the catalog schema"],
    )


def test_breaking_change_test_gap_cases() -> None:
    subject = DataChangeFact(
        key="changes",
        span=_SPAN,
        changes=[
            DataChange(
                asset_identifier="orders",
                is_breaking=True,
                downstream_assets=["dashboard", "invoice", "dashboard"],
                tested_assets=["orders", "dashboard"],
            ),
            DataChange(asset_identifier="users", is_breaking=False, downstream_assets=["profile"]),
        ],
    )
    table = fact_table(subject)
    assert value(table, data_change_test_gap_percentage) == pytest.approx(100 / 3)
    assert data_change_test_gap_percentage.policy == Numeric(maximum=5)
    empty = DataChangeFact(key="changes", span=_SPAN)
    empty_table = fact_table(empty)
    assert value(empty_table, data_change_test_gap_percentage) == 0.0


def test_asset_catalog_gap_cases() -> None:
    """Both rules read the declared assets and count what the catalog never wrote down."""
    governed = assets(
        DataAsset(identifier="orders", owners=["data"], domain="sales", is_changed=True),
        DataAsset(identifier="events", domain="product", is_changed=True),
        DataAsset(identifier="legacy", is_changed=False),
    )
    governed_table = fact_table(governed)
    assert (
        value(governed_table, data_asset_governance_gap),
        value(governed_table, data_asset_governance_gap, scope="all"),
        value(governed_table, data_asset_governance_gap, domain="optional"),
        messages(governed_table, data_asset_governance_gap, scope="all"),
    ) == (
        1,
        2,
        1,
        [
            "data asset `events` has no owner",
            "data asset `legacy` has no owner and no domain",
        ],
    )

    described = assets(
        DataAsset(
            identifier="orders",
            description="Customer orders",
            fields=[
                DataField(name="id", data_type="integer", description="Order ID"),
                DataField(name="note", data_type="string"),
            ],
        )
    )
    described_table = fact_table(described)
    assert (
        value(described_table, data_definition_gap_percentage),
        messages(described_table, data_definition_gap_percentage),
        data_definition_gap_percentage.policy,
        value(fact_table(assets()), data_definition_gap_percentage),
    ) == (
        pytest.approx(100 / 3),
        ["field `orders.note` has no description"],
        Numeric(maximum=5),
        0.0,
    )


def test_lineage_endpoint_cases() -> None:
    subject = LineageEdgeFact(
        key="lineage",
        span=_SPAN,
        edges=[
            LineageEdge(source="raw", target="clean", source_exists=True, target_exists=True),
            LineageEdge(
                source="missing", target="report", source_exists=False, target_exists=False
            ),
        ],
    )
    assert value(fact_table(subject), unresolved_lineage_endpoint) == 2


def edge(*, source: str, target: str) -> LineageEdge:
    """Return one directed lineage edge whose two endpoints the catalog holds."""
    return LineageEdge(source=source, target=target, source_exists=True, target_exists=True)


def test_unowned_high_impact_asset_cases() -> None:
    """Impact is the distinct downstream reach, and only an unowned asset with it is reported."""
    catalog = assets(
        DataAsset(identifier="raw.orders"),
        DataAsset(identifier="staging.orders"),
        DataAsset(identifier="mart.revenue", owners=["finance"]),
    )
    lineage = LineageEdgeFact(
        key="lineage",
        span=_SPAN,
        edges=[
            edge(source="raw.orders", target="staging.orders"),
            edge(source="staging.orders", target="mart.revenue"),
            edge(source="staging.orders", target="mart.invoices"),
        ],
    )
    table = fact_table(catalog, lineage)

    assert (
        value(table, unowned_high_impact_asset),
        messages(table, unowned_high_impact_asset),
        value(table, unowned_high_impact_asset, minimum_downstream=2),
        value(table, unowned_high_impact_asset, maximum_depth=1),
    ) == (
        1,
        ["data asset `raw.orders` has no owner and 3 downstream assets depend on it"],
        2,
        0,
    )


def test_ungoverned_sensitive_field_cases() -> None:
    """A sensitive tag is only reported when its owner or its glossary context is missing."""
    catalog = assets(
        DataAsset(
            identifier="orders",
            fields=[
                DataField(name="email", data_type="STRING", tags=["PII"]),
                DataField(name="total", data_type="NUMBER"),
            ],
        ),
        DataAsset(
            identifier="users",
            owners=["privacy"],
            fields=[
                DataField(
                    name="email",
                    data_type="STRING",
                    tags=["pii"],
                    glossary_terms=["Personal Data"],
                ),
                DataField(name="ssn", data_type="STRING", tags=["internal"]),
            ],
        ),
        DataAsset(
            identifier="events",
            owners=["product"],
            fields=[DataField(name="visitor_ip", data_type="STRING", tags=["sensitive"])],
        ),
    )
    table = fact_table(catalog)

    assert (
        value(table, ungoverned_sensitive_field),
        messages(table, ungoverned_sensitive_field),
    ) == (
        2,
        [
            "field `orders.email` tagged `PII` has no owner and no glossary term",
            "field `events.visitor_ip` tagged `sensitive` has no glossary term",
        ],
    )


def test_ungoverned_data_reference_cases() -> None:
    """Each source reference is judged against the governance its resolved asset records."""
    references = DataAssetReferenceFact(
        key="asset references",
        span=_SPAN,
        references=[
            asset_reference("pipeline.py:12", identifier="warehouse.orders", asset_exists=True),
            asset_reference("pipeline.py:20", identifier="warehouse.customers", asset_exists=True),
            asset_reference("pipeline.py:30", identifier="ghost", asset_exists=False),
            asset_reference("report.py:5", identifier="legacy.metrics", asset_exists=True),
        ],
    )
    catalog = assets(
        DataAsset(identifier="warehouse.orders", description="Placed orders", is_changed=True),
        DataAsset(identifier="warehouse.customers", owners=["crm"], description="Customers"),
        DataAsset(identifier="legacy.metrics"),
    )
    table = fact_table(references, catalog)

    assert (
        value(table, ungoverned_data_reference),
        messages(table, ungoverned_data_reference),
        value(table, ungoverned_data_reference, scope="changed"),
    ) == (
        2,
        [
            "data asset `warehouse.orders` read here has no owner",
            "data asset `legacy.metrics` read here has no owner and no description",
        ],
        1,
    )
