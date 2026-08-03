from typing import TYPE_CHECKING

import polars as pl

from mcmr.facts import SyntaxFact
from mcmr.table import AnalysisSession
from mcmr.table.relations import SyntaxTable

if TYPE_CHECKING:
    from pathlib import Path


def test_existing_node_text_is_reused_without_a_source_join(tmp_path: Path) -> None:
    (tmp_path / "subject.py").write_text(
        "value = 1\n",
        encoding="utf-8",
    )
    table = AnalysisSession(
        tmp_path,
        suffixes=(".py",),
        typed_families=(SyntaxFact.__name__,),
    ).syntax_tables()
    nodes = pl.DataFrame({"text": ["ready"]}).lazy()

    assert SyntaxTable(table=table).with_text(nodes) is nodes
