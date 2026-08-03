from collections.abc import Mapping, Sequence

from patos import FrozenModel, Runtime

from ...facts import Fact
from ...table import AnalysisSession, RepositoryTables


class BatchEnvironment(FrozenModel):
    """Hold invariant table state shared by connected rule batches."""

    session: Runtime[AnalysisSession]
    ordered: Sequence[type[Fact]]
    external: Runtime[RepositoryTables]
    available: set[type[Fact]]
    fix_counts: Mapping[str, int]
