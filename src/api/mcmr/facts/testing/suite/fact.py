from ...foundation import Fact


class TestSuiteFact(Fact):
    """Describe one test suite and its collected execution evidence."""

    strict_controls: dict[str, bool] = {}
    import_mode: str = "prepend"
    anyio_mode: str = ""
    asyncio_mode: str = ""
    is_coverage_configured: bool = False
    is_branch_coverage_enabled: bool = False
