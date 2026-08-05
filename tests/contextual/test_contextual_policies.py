from pathlib import Path

from mcmr import Category
from mcmr.contextual.corpus import ContextualCorpus
from mcmr.facts import (
    ClassFact,
    CloneFragment,
    CloneGroupFact,
    SourceSpan,
    SymbolFact,
)
from mcmr.plugins import fact_table
from mcmr.rules.general import (
    comment_accuracy,
    comment_intent,
    inheritance_design,
    mixed_class_responsibilities,
    module_cohesion,
    semantic_duplication,
    substitutability,
)
from mcmr.rules.python import model_foundation, shared_model_placement, shared_typing_placement

from .test_reengineered_rules import (
    analyzed,
    candidates,
    fields,
    records,
    subjects,
)


def test_placement_rules_send_one_owned_decision_per_declaration(tmp_path: Path) -> None:
    """Placement candidates keep exact ownership evidence and never fail from nomination alone."""
    (tmp_path / "shop").mkdir()
    for path, source in {
        "shop/__init__.py": "",
        "shop/types.py": (
            "from patos import FrozenModel\n\n\nclass Shared(FrozenModel):\n    value: str\n"
        ),
        "shop/first.py": """from .types import Shared


def first(value: Shared) -> str:
    return value.value
""",
        "shop/second.py": """from .types import Shared


def second(value: Shared) -> str:
    return value.value
""",
        "aliases.py": "type SharedName = str\n",
        "consumer.py": "from aliases import SharedName\n",
    }.items():
        (tmp_path / path).write_text(source)
    model_frame = candidates(shared_model_placement, analyzed(tmp_path, ClassFact))

    typing_frame = candidates(
        shared_typing_placement,
        analyzed(tmp_path, SymbolFact),
        minimum_definitions=1,
        minimum_imported_definitions=1,
        minimum_cross_module_imports=1,
    )

    typing_fields = fields(subjects(typing_frame)[0])
    assert (
        [fields(subject)["name"] for subject in subjects(model_frame)],
        typing_frame.height,
        typing_fields["name"],
        typing_fields["importing_modules"],
        typing_fields["proposed_destination"],
    ) == (["Shared"], 1, "SharedName", ["consumer.py"], "typings.py")


def test_semantic_duplication_receives_the_exact_source_from_every_copy() -> None:
    """The semantic clone judgment sees implementations rather than locations alone."""
    fact = CloneGroupFact(
        key="clone:shop/left.py:1:90",
        span=SourceSpan(path="shop/left.py"),
        language="python",
        fragments=[
            CloneFragment(
                path="shop/left.py",
                start_line=1,
                end_line=10,
                source="def tax(total):\n    return total * 0.1",
            ),
            CloneFragment(
                path="shop/right.py",
                start_line=1,
                end_line=10,
                source="def levy(total):\n    return total * 0.1",
            ),
        ],
        token_length=90,
        repository_line_count=100,
    )
    frame = candidates(semantic_duplication, fact_table(CloneGroupFact, [fact]))

    assert [record["source"] for record in records(subjects(frame)[0])] == [
        "def tax(total):\n    return total * 0.1",
        "def levy(total):\n    return total * 0.1",
    ]


def test_the_ten_policies_have_actionable_bad_categories() -> None:
    """No contextual category family is entirely neutral or accepted."""
    rules = (
        module_cohesion,
        mixed_class_responsibilities,
        inheritance_design,
        substitutability,
        comment_intent,
        comment_accuracy,
        semantic_duplication,
        model_foundation,
        shared_model_placement,
        shared_typing_placement,
    )

    assert all(isinstance(rule.policy, Category) and rule.policy.bad for rule in rules)


def test_reviewed_corpus_freezes_clear_answers_for_all_eight_rules() -> None:
    """Keep model and rubric comparisons tied to reviewed provider-real candidates."""
    corpus = ContextualCorpus.read(Path(__file__).with_name("reengineered_rules.json"))

    assert len(corpus.cases) == 17
    assert {case.rule for case in corpus.cases} == {
        "ALL-ARCH1001",
        "ALL-ARCH1004",
        "ALL-CLAS1001",
        "ALL-CLAS1002",
        "ALL-COMM1001",
        "ALL-COMM1002",
        "ALL-DUPL1001",
        "PY-MODE1001",
    }
    assert all(case.candidate.evidence for case in corpus.cases)
