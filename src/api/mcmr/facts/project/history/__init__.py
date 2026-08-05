from .change import HistoryChange
from .fact import RepositoryHistoryFact
from .file import FileHistory

RepositoryHistoryFact.model_rebuild(
    _types_namespace={"FileHistory": FileHistory, "HistoryChange": HistoryChange}
)

__all__ = ["FileHistory", "HistoryChange", "RepositoryHistoryFact"]
