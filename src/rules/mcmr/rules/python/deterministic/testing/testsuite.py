from .....facts import TestSuiteFact
from .....table.relations import FactRelations


class TestSuiteTables(FactRelations[TestSuiteFact]):
    """Expose normalized suite configuration and provider evidence."""
