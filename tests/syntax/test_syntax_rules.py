from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from mcmr.domain.contracts import RuleContract, RuleSetting, RuleValue
from mcmr.facts import SourceSpan, SyntaxFact, SyntaxNode
from mcmr.query import RuleQuery, scalar_row_value
from mcmr.rules.general import uninformative_local_name
from mcmr.table import AnalysisSession, SyntaxRelation

from ..support import written

if TYPE_CHECKING:
    from mcmr.plugins import Fact, Table

_SPAN = SourceSpan(path="src/loader.py")


def syntax_table(root: Path, sources: dict[str, str]) -> Table[SyntaxFact]:
    """Parse one source corpus into specialized native syntax relations."""
    return AnalysisSession(
        written(root, sources),
        suffixes=sorted({Path(name).suffix for name in sources}),
        typed_families=(SyntaxFact,),
    ).syntax_tables()


def query[Family: Fact](
    rule: RuleContract,
    subject: Table[Family],
    **settings: RuleSetting,
) -> RuleQuery:
    """Invoke one rule once over the complete specialized table."""
    result = rule.invoke_table(subject, settings=settings, dependencies={})
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic syntax test rule returned a model query")
    return result


def syntax_values(result: RuleQuery, subject: Table[SyntaxFact]) -> dict[str, RuleValue]:
    """Return every syntax answer by qualified declaration name."""
    facts = subject.frame(SyntaxRelation.FACTS).select("fact_id", "qualname")
    rows = result.values.collect().join(facts, on="fact_id")
    return {
        cast("str", row["qualname"]): scalar_row_value(row) for row in rows.iter_rows(named=True)
    }


def test_a_name_too_short_to_say_what_it_holds_is_reported(tmp_path: Path) -> None:
    """A brief local name is reported and a conventional index is left alone.

    A local name is the cheapest documentation a body has and the only one that cannot stale, while
    `i` in a loop is a convention older than the code and reads fine.
    """
    subject = syntax_table(
        tmp_path,
        {
            "src/loader.py": """def load():
    d = read()
    raw = read()
    r = read()


def indexes():
    i = read()
    n = read()
"""
        },
    )

    default = syntax_values(query(uninformative_local_name, subject), subject)
    permissive = syntax_values(
        query(uninformative_local_name, subject, minimum_length=1),
        subject,
    )
    assert default["load"] == 2
    assert default["indexes"] == 0
    assert permissive["load"] == 0


def test_only_a_callable_carrying_a_tree_is_judged(tmp_path: Path) -> None:
    """The rule reads the locals a callable binds and declines everything else.

    A fact carrying no tree was never asked to carry one, and `id` on a model reads fine where the
    same `id` inside a function body does not.
    """
    subject = syntax_table(
        tmp_path,
        {
            "src/loader.py": """id = read()


class Record:
    id = read()


def load():
    id = read()
"""
        },
    )
    result = query(uninformative_local_name, subject)
    facts = subject.frame(SyntaxRelation.FACTS).select("fact_id", "kind", "qualname")
    rows = result.values.collect().join(facts, on="fact_id")

    assert rows.filter(rows["kind"] != "callable").get_column("integer_value").sum() == 0
    assert syntax_values(result, subject)["load"] == 1


def test_the_tree_navigates_the_way_a_rule_reads_it() -> None:
    """Walking, narrowing by kind, and measuring depth are what make a style rule writable."""
    tree = SyntaxNode(
        kind="callable",
        name="load",
        children=[
            SyntaxNode(kind="binding", name="raw", children=[SyntaxNode(kind="call", name="read")])
        ],
    )

    assert [node.kind for node in tree.walk()] == ["callable", "binding", "call"]
    assert tree.names("call") == ["read"]
    assert [node.name for node in tree.of_kind("binding", "call")] == ["raw", "read"]
    assert tree.depth == 3
    subject = SyntaxFact(
        key="syntax:src/loader.py:load",
        span=_SPAN,
        kind="callable",
        tree=tree,
    )
    assert subject.root is tree
    assert subject.text_of(SyntaxNode(kind="name", text="retained")) == "retained"


def test_node_text_is_sliced_from_the_declaration_copy() -> None:
    """A nested node recovers exact text without serializing source on every tree node."""
    source = "def load(path):\n        value = read(path)\n        return value"
    span = SourceSpan(
        path="src/loader.py",
        start_line=10,
        start_column=4,
        end_line=12,
        end_column=20,
    )
    subject = SyntaxFact(
        key="syntax:src/loader.py:load",
        span=span,
        language="python",
        qualname="load",
        kind="callable",
        source=source,
    )

    assert subject.text_of(SyntaxNode(kind="name", span=span)) == source
    assert (
        subject.text_of(
            SyntaxNode(
                kind="binding",
                span=SourceSpan(
                    path="src/loader.py",
                    start_line=11,
                    start_column=8,
                    end_line=11,
                    end_column=26,
                ),
            )
        )
        == "value = read(path)"
    )
    assert (
        subject.text_of(
            SyntaxNode(
                kind="name",
                span=SourceSpan(
                    path="src/loader.py",
                    start_line=10,
                    start_column=8,
                    end_line=10,
                    end_column=12,
                ),
            )
        )
        == "load"
    )


def test_node_text_uses_the_providers_utf8_byte_columns() -> None:
    """A non-ASCII character before a node does not shift the parser's byte coordinates."""
    source = 'def read() -> str:\n    return "café".upper()\n'
    subject = SyntaxFact(
        key="syntax:src/reader.py:read",
        span=SourceSpan(path="src/reader.py", end_line=2, end_column=26),
        source=source,
    )
    expression = SyntaxNode(
        kind="call",
        span=SourceSpan(
            path="src/reader.py",
            start_line=2,
            start_column=11,
            end_line=2,
            end_column=26,
        ),
    )

    assert subject.text_of(expression) == '"café".upper()'

    divided = SyntaxNode(
        kind="name",
        span=SourceSpan(
            path="src/reader.py",
            start_line=2,
            start_column=16,
            end_line=2,
            end_column=17,
        ),
    )
    with pytest.raises(ValueError, match="divides a UTF-8 character"):
        subject.text_of(divided)


def test_compact_nodes_navigate_without_building_an_object_tree() -> None:
    """Provider records expose the same traversal while retaining only primitive tuples."""
    span = SourceSpan(
        path="src/loader.py",
        start_line=10,
        start_column=4,
        end_line=12,
        end_column=20,
    )
    subject = SyntaxFact(
        key="syntax:src/loader.py:load",
        span=span,
        language="python",
        qualname="load",
        kind="callable",
        source="def load(path):\n        value = read(path)\n        return value",
        nodes=[
            ("callable", "load", 10, 4, 12, 20, [1, 2]),
            ("binding", "value", 11, 8, 11, 26, [3]),
            ("return", "", 12, 8, 12, 20, []),
            ("call", "read", 11, 16, 11, 26, []),
        ],
    )

    root = subject.root
    assert root is not None
    assert [node.kind for node in root.walk()] == ["callable", "binding", "call", "return"]
    assert root.names("binding", "call") == ["value", "read"]
    assert root.depth == 3
    assert subject.text_of(root.children[0]) == "value = read(path)"


def test_node_text_rejects_locations_outside_its_declaration() -> None:
    """A provider cannot quietly turn a bad location into empty or unrelated source."""
    subject = SyntaxFact(
        key="syntax:src/loader.py:load",
        span=SourceSpan(path="src/loader.py", end_column=4),
        source="load",
    )

    with pytest.raises(ValueError, match="must carry a source span"):
        subject.text_of(SyntaxNode(kind="name"))
    with pytest.raises(ValueError, match="differs from fact path"):
        subject.text_of(
            SyntaxNode(kind="name", span=SourceSpan(path="src/other.py", end_column=4))
        )
    with pytest.raises(ValueError, match="line 2 lies outside"):
        subject.text_of(
            SyntaxNode(
                kind="name",
                span=SourceSpan(path="src/loader.py", start_line=2, end_line=2),
            )
        )
    with pytest.raises(ValueError, match="column 5 lies outside"):
        subject.text_of(
            SyntaxNode(
                kind="name",
                span=SourceSpan(path="src/loader.py", start_column=5, end_column=5),
            )
        )
