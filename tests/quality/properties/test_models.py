import pytest
from pydantic import ValidationError

from mcmr.domain.contracts import RuleDefinition
from mcmr.domain.policy import LengthDistribution
from mcmr.facts import (
    CloneFragment,
    CloneGroupFact,
    CoChangedPair,
    ComprehensionFact,
    DependencyRecord,
    EscapeHatch,
    ExceptionRegion,
    FileHistory,
    HistoryChange,
    KernelLaunchFact,
    MemberDeclaration,
    ModuleSurfaceFact,
    NodeRef,
    OverrideFact,
    PythonTargetConfiguration,
    RepeatedStringExpression,
    RepositoryHistoryFact,
    SourceSpan,
    SyntaxFact,
    SyntaxNode,
    Waiver,
)
from mcmr.facts import (
    TestFunction as CaseFunction,
)

from ...support import built_catalog, family_of
from .support import readers, specialized_families


def test_clone_models_refuse_impossible_relationships() -> None:
    """Clone geometry agrees with the fragments it contains."""
    with pytest.raises(ValidationError, match="repeats 10 lines"):
        CloneGroupFact(
            key="clones:shop",
            span=SourceSpan(path="shop/left.py"),
            token_length=40,
            repository_line_count=4,
            fragments=[
                CloneFragment(path="shop/left.py", start_line=1, end_line=10),
                CloneFragment(path="shop/right.py", start_line=1, end_line=10),
            ],
        )
    with pytest.raises(ValidationError, match="greater than or equal to 40"):
        CloneGroupFact(
            key="clones:shop",
            span=SourceSpan(path="shop/left.py"),
            token_length=39,
            repository_line_count=20,
            fragments=[
                CloneFragment(path="shop/left.py", start_line=1, end_line=10),
                CloneFragment(path="shop/right.py", start_line=1, end_line=10),
            ],
        )
    with pytest.raises(ValidationError, match="before line"):
        CloneFragment(path="shop/left.py", start_line=10, end_line=2)
    with pytest.raises(ValidationError, match="at least 2 items"):
        CloneGroupFact(
            key="clones:shop",
            span=SourceSpan(path="shop/left.py"),
            token_length=40,
            repository_line_count=10,
            fragments=[CloneFragment(path="shop/left.py", start_line=1, end_line=10)],
        )
    with pytest.raises(ValidationError, match="overlap"):
        CloneGroupFact(
            key="clones:shop",
            span=SourceSpan(path="shop/left.py"),
            token_length=40,
            repository_line_count=20,
            fragments=[
                CloneFragment(path="shop/left.py", start_line=1, end_line=10),
                CloneFragment(path="shop/left.py", start_line=5, end_line=14),
            ],
        )


def test_override_models_refuse_repeated_members() -> None:
    """Override providers cannot repeat one declaration inside a class."""
    with pytest.raises(ValidationError, match="repeats a declared member name"):
        OverrideFact(
            key="override:shop.Report",
            span=SourceSpan(path="shop/report.py"),
            declared=[MemberDeclaration(name="run"), MemberDeclaration(name="run")],
        )


def test_fact_models_refuse_counts_that_could_escape_a_rule_contract() -> None:
    """A provider cannot state a negative count or a numerator larger than its denominator."""
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        ComprehensionFact(
            key="comprehensions:shop/service.py",
            span=SourceSpan(path="shop/service.py"),
            loop_counts=[-2],
        )
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        ExceptionRegion(clause_statement_counts=[-2])
    with pytest.raises(ValidationError, match="greater than 0"):
        LengthDistribution(root=[0])
    with pytest.raises(ValidationError, match="predates"):
        DependencyRecord(
            name="library",
            resolved_release_day=20,
            latest_compatible_release_day=10,
        )


def test_fact_models_refuse_negative_provider_values() -> None:
    """Provider records reject negative values before any rule can read them."""
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        PythonTargetConfiguration(tool_target_minors={"ruff": -1})
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        CaseFunction(name="test_one", path="tests/test_one.py", parametrized_range_sizes=[-1])
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        Waiver(location="src/service.py:2", age_days=-1)


def test_source_spans_refuse_impossible_locations() -> None:
    """A source range is ordered and stays inside its repository."""
    point = SourceSpan(path="src/service.py", start_line=4, start_column=3)
    assert (point.location, point.model_dump()) == (
        "src/service.py:4",
        {
            "path": "src/service.py",
            "start_line": 4,
            "start_column": 3,
            "end_line": 4,
            "end_column": 3,
        },
    )
    invalid = [
        ({"path": "src/service.py", "start_line": 4, "end_line": 3}, "ends on line"),
        ({"path": "src/service.py", "start_column": 4, "end_column": 3}, "ends at column"),
        ({"path": "/tmp/service.py"}, "repository relative"),
        ({"path": "../service.py"}, "leave the repository"),
        ({"path": r"src\service.py"}, "forward slashes"),
    ]
    for fields, message in invalid:
        with pytest.raises(ValidationError, match=message):
            SourceSpan.model_validate(fields)


def test_provider_models_refuse_impossible_counts_and_paths() -> None:
    """Module surfaces refuse counts outside the physical source."""
    with pytest.raises(ValidationError, match="2 escape hatches"):
        ModuleSurfaceFact(
            key="surface:src/index.ts",
            span=SourceSpan(path="src/index.ts"),
            physical_line_count=1,
            escape_hatches=[EscapeHatch(kind="any"), EscapeHatch(kind="any")],
        )
    with pytest.raises(ValidationError, match="beyond its physical lines"):
        ModuleSurfaceFact(
            key="surface:src/index.ts",
            span=SourceSpan(path="src/index.ts"),
            physical_line_count=2,
            escape_hatches=[EscapeHatch(kind="any", line=3)],
        )


def test_history_models_refuse_impossible_counts_and_paths() -> None:
    """History providers refuse negative counts, empty paths, and repeated changes."""
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        FileHistory(path="shop/service.py", author_count=2, additional_commit_count=-1)
    with pytest.raises(ValidationError, match="at least 1 character"):
        FileHistory(path="")
    with pytest.raises(ValidationError, match="repeat a changed path"):
        HistoryChange(paths=["shop/service.py", "shop/service.py"])
    with pytest.raises(ValidationError, match="at least 1 character"):
        HistoryChange(paths=[""])


def test_history_models_refuse_impossible_relationships() -> None:
    """History providers refuse relationships their surrounding evidence disproves."""
    with pytest.raises(ValidationError, match="file cannot outnumber repository commits"):
        RepositoryHistoryFact(
            key="history",
            span=SourceSpan(path=""),
            files=[FileHistory(path="shop/service.py", author_count=2)],
        )
    with pytest.raises(ValidationError, match="repeat a file"):
        RepositoryHistoryFact(
            key="history",
            span=SourceSpan(path=""),
            unscoped_commit_count=1,
            files=[FileHistory(path="shop/service.py"), FileHistory(path="shop/service.py")],
        )
    with pytest.raises(ValidationError, match="co-changed with itself"):
        CoChangedPair(
            left="shop/service.py",
            right="shop/service.py",
            shared_commit_count=1,
            left_commit_count=1,
            right_commit_count=1,
        )
    with pytest.raises(ValidationError, match="shared commits cannot outnumber"):
        CoChangedPair(
            left="shop/service.py",
            right="shop/api.py",
            shared_commit_count=3,
            left_commit_count=2,
            right_commit_count=3,
        )


def test_syntax_models_refuse_impossible_relationships() -> None:
    """Syntax providers refuse empty values while preserving useful separators."""
    with pytest.raises(ValidationError, match="at least 1 character"):
        KernelLaunchFact(
            key="launch:src/kernel.cu:scale",
            span=SourceSpan(path="src/kernel.cu"),
            kernel="scale",
            grid="",
            block="threads",
        )
    with pytest.raises(ValidationError, match="at least 1 character"):
        RepeatedStringExpression(
            literal="",
            repetition_count=4,
            node=NodeRef(id="empty", span=SourceSpan(path="src/example.py")),
        )
    assert (
        RepeatedStringExpression(
            literal="=-",
            repetition_count=2,
            node=NodeRef(id="separator", span=SourceSpan(path="src/example.py")),
        ).literal
        == "=-"
    )
    assert (
        RepeatedStringExpression(
            literal=" ",
            repetition_count=2,
            node=NodeRef(id="space", span=SourceSpan(path="src/example.py")),
        ).literal
        == " "
    )


@pytest.mark.parametrize(
    ("nodes", "message"),
    [
        ([("type", "run", 1, 0, 2, 4, [])], "root kind"),
        ([("callable", "run", 1, 1, 2, 4, [])], "root span"),
        (
            [
                ("callable", "run", 1, 0, 2, 4, [1]),
                ("statement", "", 2, 3, 2, 2, []),
            ],
            "ends before",
        ),
        (
            [
                ("callable", "run", 1, 0, 2, 4, [1]),
                ("statement", "", 3, 0, 3, 1, []),
            ],
            "outside its declaration",
        ),
        ([("callable", "run", 1, 0, 2, 4, [1])], "missing child"),
        (
            [
                ("callable", "run", 1, 0, 2, 4, [1]),
                ("statement", "", 2, 0, 2, 4, [1]),
            ],
            "more than one parent",
        ),
        (
            [
                ("callable", "run", 1, 0, 2, 4, []),
                ("statement", "", 2, 0, 2, 4, []),
            ],
            "unreachable from the root",
        ),
    ],
)
def test_compact_syntax_records_must_form_one_located_tree(
    nodes: list[tuple[str, str, int, int, int, int, list[int]]], message: str
) -> None:
    """A malformed provider tree is rejected instead of producing partial rule answers."""
    with pytest.raises(ValidationError, match=message):
        SyntaxFact(
            key="syntax:src/service.py:run",
            span=SourceSpan(path="src/service.py", end_line=2, end_column=4),
            kind="callable",
            nodes=nodes,
        )


def test_a_syntax_fact_carries_only_one_tree_representation() -> None:
    """Fixtures may use object trees and providers may use records, but never both together."""
    with pytest.raises(ValidationError, match="root kind"):
        SyntaxFact(
            key="syntax:src/service.py:run",
            span=SourceSpan(path="src/service.py"),
            kind="callable",
            tree=SyntaxNode(kind="type"),
        )

    with pytest.raises(ValidationError, match="both expanded and compact"):
        SyntaxFact(
            key="syntax:src/service.py:run",
            span=SourceSpan(path="src/service.py", end_column=3),
            kind="callable",
            tree=SyntaxNode(kind="callable", text="run"),
            nodes=[("callable", "run", 1, 0, 1, 3, [])],
        )

    with pytest.raises(ValidationError, match="differs from fact path"):
        SyntaxFact(
            key="syntax:src/service.py:run",
            span=SourceSpan(path="src/service.py"),
            kind="callable",
            tree=SyntaxNode(
                kind="callable",
                children=[SyntaxNode(kind="name", span=SourceSpan(path="src/other.py"))],
            ),
        )


def test_every_rule_declares_its_complete_table_contract() -> None:
    """Every rule exposes resolvable table dependencies without a parallel plan registry."""

    def verify(definition: RuleDefinition) -> None:
        rule = by_path[definition.callable]
        assert rule.table_native, definition.id
        assert rule.tables, definition.id
        assert definition.tables == [family.__name__ for _, family in rule.tables]
        assert definition.fact == rule.primary_family.__name__

    catalog = built_catalog()
    by_path = {rule.callable_path: rule for rule in catalog.rules}
    swept = {definition.id for group in readers().values() for _, definition in group}
    generic = {
        definition.id
        for definition in catalog.definitions
        if definition.lane == "deterministic"
        and not by_path[definition.callable].injected
        and len(by_path[definition.callable].tables) == 1
        and family_of(by_path[definition.callable]) not in specialized_families()
    }

    assert swept == generic
    for definition in catalog.definitions:
        verify(definition)
