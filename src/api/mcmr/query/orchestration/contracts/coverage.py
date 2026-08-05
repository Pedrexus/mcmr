from patos import Model

from ....kernel import KernelStats


class TableCoverage(Model):
    """Report what one table execution reached across the analyzed repository."""

    kernel: KernelStats = KernelStats()
    runnable: set[str] = set()
    languages: set[str] = set()
    read_families: set[str] = set()

    @property
    def provider_read_count(self) -> int:
        """Return how many distinct fact families the selected rules read."""
        return len(self.read_families)
