from typing import TYPE_CHECKING

import pytest

from mcmr.accounting.upstream import (
    ClaimIndex,
    ToolCoverage,
    ToolRegistry,
)
from mcmr.rulebook.catalog import Catalog, RuleDefinition
from mcmr.rulebook.discovery import RuleModuleDiscovery

if TYPE_CHECKING:
    from collections.abc import Sequence

_INVENTORIED = [profile.slug for profile in ToolRegistry().profiles if profile.inventoried]
_INVENTORY_SIZES = {
    "pylint": 389,
    "ruff": 968,
    "clippy": 809,
    "clang-tidy": 604,
    "eslint": 292,
    "typescript-eslint": 134,
    "cppcheck": 342,
}


@pytest.fixture(scope="module")
def definitions() -> list[RuleDefinition]:
    """Return every rule the catalog validates, which is where provenance now lives."""
    return list(Catalog(modules=RuleModuleDiscovery().modules).definitions)


@pytest.fixture(scope="module")
def claims(definitions: Sequence[RuleDefinition]) -> ClaimIndex:
    """Return every coverage claim read back out of those rules' own docstrings."""
    return ClaimIndex(definitions=definitions)


@pytest.fixture(scope="module")
def report(claims: ClaimIndex) -> ToolCoverage:
    """Return the Pylint account, which is the one with a written gap for every message."""
    return ToolCoverage(tool="pylint", claims=claims)


def inventoried() -> list[str]:
    """Return registered tools backed by frozen inventories."""
    return list(_INVENTORIED)


def inventory_sizes() -> dict[str, int]:
    """Return expected rule counts for every frozen inventory."""
    return dict(_INVENTORY_SIZES)
