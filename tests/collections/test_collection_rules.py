from mcmr.domain.contracts import RuleContract, RuleSetting, RuleValue
from mcmr.facts import (
    CollectionFact,
    ComprehensionFact,
    Fact,
    LocalCollection,
    NodeRef,
    PairSequence,
    ParameterFact,
    ParameterUse,
    SetLoopCandidate,
    SourceSpan,
)
from mcmr.query import scalar_frame_value
from mcmr.rules.python import (
    comprehension_loop_count,
    concrete_collection_parameter,
    literal_pair_sequence_mapping_candidate,
    local_collection_representation_candidate,
    manual_set_comprehension,
)

from ..support import retained_query as query

_SPAN = SourceSpan(path="src/example.py")


def value(subject: Fact, rule: RuleContract, **settings: RuleSetting) -> RuleValue:
    """Return the one scalar emitted for the retained test fact."""
    return scalar_frame_value(query(subject, rule, **settings).values.collect())


def test_collection_parameter_cases() -> None:
    subject = ParameterFact(
        key="parameters",
        span=_SPAN,
        parameters=[
            ParameterUse(annotation="list", operations=["iterate", "contains"]),
            ParameterUse(annotation="list", operations=["append"]),
        ],
    )
    assert value(subject, concrete_collection_parameter) is True
    assert (
        value(
            subject.model_copy(update={"parameters": subject.parameters[1:]}),
            concrete_collection_parameter,
        )
        is False
    )


def test_collection_representation_cases() -> None:
    subject = CollectionFact(
        key="collections",
        span=_SPAN,
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
    assert value(subject, literal_pair_sequence_mapping_candidate) == 1
    assert value(subject, local_collection_representation_candidate) == 2
    assert (
        value(
            subject,
            local_collection_representation_candidate,
            sequence_preference="tuple",
            prefer_membership_set=False,
        )
        == 0
    )


def comprehension_subject() -> ComprehensionFact:
    """Return one comprehension fact with a safe and an unsafe set loop."""
    return ComprehensionFact(
        key="comprehensions",
        span=_SPAN,
        loop_counts=[1, 3, 2],
        set_loop_candidates=[
            SetLoopCandidate(
                name="seen",
                has_unshadowed_set_initialization=True,
                loop_is_synchronous=True,
                only_effect_is_add=True,
                conditional_count=1,
                initialization=NodeRef(id="init", span=_SPAN, text="seen = set()"),
                loop=NodeRef(id="loop", span=_SPAN, text="for item in items:"),
                element=NodeRef(id="element", span=_SPAN, text="item.key"),
                target=NodeRef(id="target", span=_SPAN, text="item"),
                iterable=NodeRef(id="iterable", span=_SPAN, text="items"),
                conditions=[NodeRef(id="condition", span=_SPAN, text="item.is_active")],
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


def test_comprehension_measurement_cases() -> None:
    subject = comprehension_subject()
    assert (
        value(subject, comprehension_loop_count),
        value(subject, manual_set_comprehension),
        value(subject.model_copy(update={"loop_counts": []}), comprehension_loop_count),
    ) == (3, 1, 0)


def test_manual_set_comprehension_fixes_require_complete_evidence() -> None:
    subject = comprehension_subject()
    assert (fix := query(subject, manual_set_comprehension).fix) is not None
    rewrites = fix.rewrites.collect().sort("rewrite_order")
    assert (
        rewrites.get_column("kind").to_list(),
        rewrites.filter(rewrites["kind"] == "replace").item(0, "source"),
    ) == (
        ["replace", "remove"],
        "seen = {item.key for item in items if item.is_active}",
    )
    partial = subject.set_loop_candidates[0].model_copy(update={"element": None})
    partial_fix = query(
        subject.model_copy(update={"set_loop_candidates": [partial]}),
        manual_set_comprehension,
    ).fix
    unaddressed = subject.set_loop_candidates[0].model_copy(update={"initialization": None})
    unaddressed_fix = query(
        subject.model_copy(update={"set_loop_candidates": [unaddressed]}),
        manual_set_comprehension,
    ).fix
    assert partial_fix is not None and unaddressed_fix is not None
    assert (
        partial_fix.rewrites.collect().is_empty(),
        unaddressed_fix.rewrites.collect().is_empty(),
    ) == (True, True)
