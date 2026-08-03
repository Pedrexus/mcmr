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
    Fact,
    LineageEdge,
    LineageEdgeFact,
    SourceSpan,
)
from mcmr.query import RuleQuery, scalar_row_value
from mcmr.rules.general import (
    data_asset_governance_gap,
    data_change_test_gap_percentage,
    data_definition_gap_percentage,
    incompatible_data_field_type,
    missing_data_asset_reference,
    missing_data_field_reference,
    nonactive_data_asset_reference,
    unhealthy_data_dependency,
    unresolved_lineage_endpoint,
)
from mcmr.table import Table
from mcmr.table import fact_table as in_memory_table

if TYPE_CHECKING:
    from ..support import Declared

_SPAN = SourceSpan(path="catalog")


def fact_table[Family: Fact](first: Family, *rest: Family) -> Table[Fact]:
    """Normalize one or more facts through a single in-memory native table."""
    subjects = (first, *rest)
    return in_memory_table(type(first), subjects)


def query(
    subject: Table[Fact],
    rule: RuleContract,
    **settings: RuleSetting,
) -> RuleQuery:
    """Execute one deterministic rule once over a retained table."""
    result = rule.invoke_table(subject, settings=settings, dependencies={})
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic data asset rule returned a model query")
    return result


def values(result: RuleQuery) -> list[RuleValue]:
    """Return every scalar emitted by one table query in fact order."""
    return [scalar_row_value(row) for row in result.values.collect().iter_rows(named=True)]


def value(
    subject: Table[Fact],
    rule: RuleContract,
    **settings: RuleSetting,
) -> RuleValue:
    """Return the one scalar emitted for a single retained fact."""
    answers = values(query(subject, rule, **settings))
    if len(answers) != 1:
        raise ValueError(f"expected one data asset value and received {len(answers)}")
    return answers[0]


def asset_reference(location: str, *, identifier: str, **declared: Declared) -> DataAssetReference:
    """Return one reference to a data asset, carrying what the catalog resolved about it."""
    return DataAssetReference.model_validate(
        {"source_location": location, "asset_identifier": identifier} | declared
    )


def field_reference(
    location: str, *, identifier: str, field: str, **declared: Declared
) -> DataFieldReference:
    """Return one reference to a field of a data asset, and what the catalog resolved of it."""
    named = {"source_location": location, "asset_identifier": identifier, "field_name": field}
    return DataFieldReference.model_validate(named | declared)


def assets(*declared: DataAsset) -> DataAssetFact:
    """Return one catalog fact holding the given declared data assets."""
    return DataAssetFact(key="assets", span=_SPAN, assets=list(declared))


def changes(*declared: DataChange) -> DataChangeFact:
    """Return one fact holding the given changes made to declared data assets."""
    return DataChangeFact(key="changes", span=_SPAN, changes=list(declared))


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
    assert value(reference_table, missing_data_asset_reference) == 1
    assert value(reference_table, nonactive_data_asset_reference) == 1
    assert value(reference_table, unhealthy_data_dependency) == 1

    fields = DataFieldReferenceFact(
        key="field references",
        span=_SPAN,
        references=[
            field_reference(
                "a.py:1", identifier="missing", field="id", asset_exists=False, field_exists=False
            ),
            field_reference(
                "b.py:1",
                identifier="orders",
                field="missing",
                asset_exists=True,
                field_exists=False,
            ),
            field_reference(
                "c.py:1",
                identifier="orders",
                field="amount",
                asset_exists=True,
                field_exists=True,
                expected_type=" DECIMAL ",
                catalog_type="decimal",
            ),
            field_reference(
                "d.py:1",
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
    assert value(field_table, missing_data_field_reference) == 1
    assert value(field_table, incompatible_data_field_type) == 1


def test_breaking_change_test_gap_cases() -> None:
    subject = changes(
        DataChange(
            asset_identifier="orders",
            is_breaking=True,
            downstream_assets=["dashboard", "invoice", "dashboard"],
            tested_assets=["orders", "dashboard"],
        ),
        DataChange(asset_identifier="users", is_breaking=False, downstream_assets=["profile"]),
    )
    table = fact_table(subject)
    assert value(table, data_change_test_gap_percentage) == pytest.approx(100 / 3)
    assert data_change_test_gap_percentage.policy == Numeric(maximum=5)
    empty = changes()
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
    assert value(governed_table, data_asset_governance_gap) == 1
    assert value(governed_table, data_asset_governance_gap, scope="all") == 2
    assert value(governed_table, data_asset_governance_gap, domain="optional") == 1

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
    assert value(fact_table(described), data_definition_gap_percentage) == pytest.approx(100 / 3)
    assert data_definition_gap_percentage.policy == Numeric(maximum=5)
    assert value(fact_table(assets()), data_definition_gap_percentage) == 0.0


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
