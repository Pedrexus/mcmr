from datetime import UTC, date, datetime, time
from typing import Annotated

from annotated_types import Ge, Le
from patos import FrozenModel
from pydantic import PositiveInt

from mcmr.plugins import NonEmptyStr

type DataHubPageSize = Annotated[int, Ge(1), Le(50)]


class DataHubCatalogRequest(FrozenModel):
    """Bound one catalog read and say which assets it treats as recently changed."""

    query: NonEmptyStr = "*"
    page_size: DataHubPageSize = 50
    max_assets: PositiveInt = 500
    since: date | None = None

    @property
    def changed_after(self) -> int | None:
        """Return midnight of the configured day in the epoch milliseconds DataHub records."""
        if self.since is None:
            return None
        return int(datetime.combine(self.since, time(), tzinfo=UTC).timestamp() * 1000)
