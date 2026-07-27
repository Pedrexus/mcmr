from mcmr.facts import (
    CollectionFact,
    ComprehensionFact,
    LocalCollection,
    NodeRef,
    PairSequence,
    ParameterFact,
    ParameterUse,
    SetLoopCandidate,
    SourceSpan,
)
from mcmr.models import Replace
from mcmr.rules.python.deterministic.collections.r0001 import concrete_collection_parameter
from mcmr.rules.python.deterministic.collections.r0002 import (
    literal_pair_sequence_mapping_candidate,
)
from mcmr.rules.python.deterministic.collections.r0003 import (
    local_collection_representation_candidate,
)
from mcmr.rules.python.deterministic.comprehensions.r0002 import comprehension_loop_count
from mcmr.rules.python.deterministic.comprehensions.r0003 import (
    manual_set_comprehension,
    use_set_comprehension,
)

SPAN = SourceSpan(path="src/example.py")


def test_collection_parameter_cases() -> None:
    subject = ParameterFact(
        key="parameters",
        span=SPAN,
        parameters=[
            ParameterUse(annotation="list", operations=["iterate", "contains"]),
            ParameterUse(annotation="list", operations=["append"]),
        ],
    )
    assert concrete_collection_parameter(subject).value
    assert not concrete_collection_parameter(
        subject.model_copy(update={"parameters": subject.parameters[1:]})
    ).value


def test_collection_representation_cases() -> None:
    subject = CollectionFact(
        key="collections",
        span=SPAN,
        pair_sequences=[
            PairSequence(
                pair_count=3,
                keys_are_unique_literals=True,
                has_single_assignment=True,
                all_reads_are_lookup_loops=True,
            ),
            PairSequence(
                pair_count=3,
                keys_are_unique_literals=False,
                has_single_assignment=True,
                all_reads_are_lookup_loops=True,
            ),
        ],
        local_collections=[
            LocalCollection(
                kind="tuple",
                value_count=3,
                has_homogeneous_literals=True,
                all_reads_are_iteration=True,
            ),
            LocalCollection(
                kind="list",
                value_count=3,
                has_homogeneous_literals=True,
                all_reads_are_membership=True,
                values_are_unique=True,
            ),
        ],
    )
    assert literal_pair_sequence_mapping_candidate(subject) == 1
    assert local_collection_representation_candidate(subject) == 2
    assert (
        local_collection_representation_candidate(
            subject,
            sequence_preference="tuple",
            prefer_membership_set=False,
        )
        == 0
    )


def test_comprehension_cases() -> None:
    subject = ComprehensionFact(
        key="comprehensions",
        span=SPAN,
        loop_counts=[1, 3, 2],
        set_loop_candidates=[
            SetLoopCandidate(
                name="seen",
                has_unshadowed_set_initialization=True,
                loop_is_synchronous=True,
                only_effect_is_add=True,
                conditional_count=1,
                initialization=NodeRef(id="init", span=SPAN, text="seen = set()"),
                loop=NodeRef(id="loop", span=SPAN, text="for item in items:"),
                element=NodeRef(id="element", span=SPAN, text="item.key"),
                target=NodeRef(id="target", span=SPAN, text="item"),
                iterable=NodeRef(id="iterable", span=SPAN, text="items"),
                conditions=[NodeRef(id="condition", span=SPAN, text="item.is_active")],
            ),
            SetLoopCandidate(
                has_unshadowed_set_initialization=True,
                loop_is_synchronous=True,
                only_effect_is_add=True,
                conditional_count=1,
                has_else=True,
            ),
        ],
    )
    assert comprehension_loop_count(subject) == 3
    assert manual_set_comprehension(subject) == 1
    assert comprehension_loop_count(subject.model_copy(update={"loop_counts": []})) == 0

    plan = use_set_comprehension(subject)
    assert plan is not None
    assert [rewrite.kind for rewrite in plan.rewrites] == ["replace", "remove"]
    assert [r.source for r in plan.rewrites if isinstance(r, Replace)] == [
        "seen = {item.key for item in items if item.is_active}"
    ]
    partial = subject.set_loop_candidates[0].model_copy(update={"element": None})
    assert (
        use_set_comprehension(subject.model_copy(update={"set_loop_candidates": [partial]}))
        is None
    )
    unaddressed = subject.set_loop_candidates[0].model_copy(update={"initialization": None})
    assert (
        use_set_comprehension(subject.model_copy(update={"set_loop_candidates": [unaddressed]}))
        is None
    )
