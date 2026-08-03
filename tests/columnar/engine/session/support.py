import sys
from typing import TYPE_CHECKING, cast

from mcmr.execution.queries import ModelQuery
from mcmr.kernel_tables import AnalysisSession as NativeAnalysisSession
from mcmr.query import table_schema
from mcmr.table import GenericRelation, Table

if TYPE_CHECKING:
    from enum import StrEnum
    from pathlib import Path

    import polars as pl

    from mcmr.facts import ClassFact, FunctionFact


def repository(tmp_path: Path) -> Path:
    """Write one small callable corpus for the native table boundary."""
    (tmp_path / "sample.py").write_text(
        """from functools import cache


@cache
def choose(flag: bool, value: int = 1) -> int:
    if flag:
        return value
    return 0
"""
    )
    return tmp_path


def contextual_repository(tmp_path: Path) -> Path:
    """Write nested candidate data for both specialized contextual families."""
    (tmp_path / "domain.py").write_text(
        """from abc import ABC, abstractmethod
from functools import cache

class MessageContent:
    pass

class MessageKind:
    pass

class Base(ABC):
    @classmethod
    @abstractmethod
    def build(cls, name: str) -> 'Base':
        raise NotImplementedError

class Child(Base):
    @classmethod
    def build(cls, name: str) -> 'Child':
        return cls()

    @staticmethod
    def create(name: str) -> 'Child':
        return Child.build(name)

@cache
def choose(flag: bool, value: int = 1) -> int:
    if flag:
        return value
    return 0

def render(definition):
    return {
        'id': definition.id,
        'summary': definition.summary,
        'scope': definition.scope,
        'lane': definition.lane,
    }
""",
        encoding="utf-8",
    )
    for name in ("api.py", "jobs.py"):
        (tmp_path / name).write_text(
            "from domain import MessageContent, MessageKind\n",
            encoding="utf-8",
        )
    models = tmp_path / "models"
    models.mkdir()
    (models / "__init__.py").write_text("", encoding="utf-8")
    (models / "records.py").write_text(
        """from pydantic import BaseModel

class First(BaseModel):
    value: int

class Second(BaseModel):
    value: int
""",
        encoding="utf-8",
    )
    return tmp_path


def direct_generic_repository(tmp_path: Path) -> Path:
    """Write evidence that exercises specialized records and nested scalar values."""
    (tmp_path / "expressions.py").write_text(
        """from enum import StrEnum

class Color(StrEnum):
    RED = 'red'

def render(color: Color) -> str:
    private = color._name_
    encoded = color.value
    separator = '-' * 8
    message = ('first\n' 'second\n')
    return f'{private}{encoded}{separator}{message}'
""",
        encoding="utf-8",
    )
    return tmp_path


def generic_model_candidates(root: Path, family: type[ClassFact | FunctionFact]) -> pl.DataFrame:
    """Build the former schema-normalized mirror as a parity oracle."""
    native = NativeAnalysisSession(
        root,
        [family.__name__],
        python_standard_library=sorted(sys.stdlib_module_names),
        suffixes=[".py"],
        generic_schemas={family.__name__: table_schema(family)},
    )
    generic = native.table(family.__name__)
    table = Table(
        family=family,
        relation_type=GenericRelation,
        frames=cast(
            "dict[StrEnum, pl.DataFrame]",
            {
                GenericRelation.FACTS: generic.facts,
                GenericRelation.RECORDS: generic.records,
                GenericRelation.VALUES: generic.values,
            },
        ),
    )
    return ModelQuery.candidate_relation(table).collect().sort("fact_order")
