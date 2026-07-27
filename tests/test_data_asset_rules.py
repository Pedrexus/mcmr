from typing import TYPE_CHECKING

import pytest

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
from mcmr.rules.general.deterministic.data_assets.r0001 import (
    missing_data_asset_reference,
)
from mcmr.rules.general.deterministic.data_assets.r0002 import (
    missing_data_field_reference,
)
from mcmr.rules.general.deterministic.data_assets.r0003 import incompatible_data_field_type
from mcmr.rules.general.deterministic.data_assets.r0004 import nonactive_data_asset_reference
from mcmr.rules.general.deterministic.data_assets.r0005 import breaking_data_change_impact
from mcmr.rules.general.deterministic.data_assets.r0006 import unhealthy_data_dependency
from mcmr.rules.general.deterministic.data_assets.r0007 import data_asset_governance_gap
from mcmr.rules.general.deterministic.data_assets.r0008 import (
    data_change_test_gap_percentage,
)
from mcmr.rules.general.deterministic.data_assets.r0009 import (
    data_definition_gap_percentage,
)
from mcmr.rules.general.deterministic.data_assets.r0010 import unresolved_lineage_endpoint

if TYPE_CHECKING:
    from tests.conftest import Declared

SPAN = SourceSpan(path="catalog")


def asset_reference(location: str, identifier: str, **declared: Declared) -> DataAssetReference:
    """Return one reference to a data asset, carrying what the catalog resolved about it."""
    return DataAssetReference.model_validate(
        {"source_location": location, "asset_identifier": identifier} | declared
    )


def field_reference(
    location: str, identifier: str, field: str, **declared: Declared
) -> DataFieldReference:
    """Return one reference to a field of a data asset, and what the catalog resolved of it."""
    named = {"source_location": location, "asset_identifier": identifier, "field_name": field}
    return DataFieldReference.model_validate(named | declared)


def assets(*declared: DataAsset) -> DataAssetFact:
    """Return one catalog fact holding the given declared data assets."""
    return DataAssetFact(key="assets", span=SPAN, assets=list(declared))


def changes(*declared: DataChange) -> DataChangeFact:
    """Return one fact holding the given changes made to declared data assets."""
    return DataChangeFact(key="changes", span=SPAN, changes=list(declared))


def test_reference_resolution_cases() -> None:
    """Each rule counts the references the catalog could not answer for, by asset and by field."""
    references = DataAssetReferenceFact(
        key="asset references",
        span=SPAN,
        references=[
            asset_reference("a.py:1", "orders", asset_exists=False),
            asset_reference(
                "b.py:1",
                "users",
                asset_exists=True,
                lifecycle="deprecated",
                upstream_health={"warehouse": "unhealthy", "raw_users": "unknown"},
            ),
            asset_reference(
                "c.py:1",
                "events",
                asset_exists=True,
                lifecycle="active",
                upstream_health={"collector": "healthy"},
            ),
        ],
    )
    assert missing_data_asset_reference(references) == 1
    assert nonactive_data_asset_reference(references) == 1
    assert unhealthy_data_dependency(references) == 1

    fields = DataFieldReferenceFact(
        key="field references",
        span=SPAN,
        references=[
            field_reference("a.py:1", "missing", "id", asset_exists=False, field_exists=False),
            field_reference("b.py:1", "orders", "missing", asset_exists=True, field_exists=False),
            field_reference(
                "c.py:1",
                "orders",
                "amount",
                asset_exists=True,
                field_exists=True,
                expected_type=" DECIMAL ",
                catalog_type="decimal",
            ),
            field_reference(
                "d.py:1",
                "orders",
                "created_at",
                asset_exists=True,
                field_exists=True,
                expected_type="timestamp",
                catalog_type="string",
            ),
        ],
    )
    assert missing_data_field_reference(fields) == 1
    assert incompatible_data_field_type(fields) == 1


def test_breaking_change_impact_and_test_gap_cases() -> None:
    subject = changes(
        DataChange(
            asset_identifier="orders",
            is_breaking=True,
            downstream_assets=["dashboard", "invoice", "dashboard"],
            tested_assets=["orders", "dashboard"],
        ),
        DataChange(asset_identifier="users", is_breaking=False, downstream_assets=["profile"]),
    )
    assert breaking_data_change_impact(subject) == 3
    assert data_change_test_gap_percentage(subject) == pytest.approx(100 / 3)
    empty = changes()
    assert breaking_data_change_impact(empty) == 0
    assert data_change_test_gap_percentage(empty) == 0.0


def test_asset_catalog_gap_cases() -> None:
    """Both rules read the declared assets and count what the catalog never wrote down."""
    governed = assets(
        DataAsset(identifier="orders", owners=["data"], domain="sales", is_changed=True),
        DataAsset(identifier="events", domain="product", is_changed=True),
        DataAsset(identifier="legacy", is_changed=False),
    )
    assert data_asset_governance_gap(governed) == 1
    assert data_asset_governance_gap(governed, changed_only=False) == 2
    assert data_asset_governance_gap(governed, require_domain=False) == 1

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
    assert data_definition_gap_percentage(described) == pytest.approx(100 / 3)
    assert data_definition_gap_percentage(assets()) == 0.0


def test_lineage_endpoint_cases() -> None:
    subject = LineageEdgeFact(
        key="lineage",
        span=SPAN,
        edges=[
            LineageEdge(source="raw", target="clean", source_exists=True, target_exists=True),
            LineageEdge(
                source="missing", target="report", source_exists=False, target_exists=False
            ),
        ],
    )
    assert unresolved_lineage_endpoint(subject) == 2
