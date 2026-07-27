from mcmr.facts import (
    BranchFact,
    CallFact,
    CallSite,
    CommentFact,
    CommentGroup,
    ConditionalArm,
    ConditionalChain,
    ControlIncrement,
    ControlKind,
    FunctionFact,
    FunctionParameter,
    KernelLaunchFact,
    ParameterFact,
    ParameterUse,
    SourceSpan,
)
from mcmr.rules.cuda.deterministic.launch.r0001 import raw_barrier_over_cooperative_groups
from mcmr.rules.cuda.deterministic.launch.r0002 import default_stream_kernel_launch
from mcmr.rules.cuda.deterministic.memory.r0001 import synchronous_transfer_in_stream_scope
from mcmr.rules.general.deterministic.branches.r0001 import value_dispatch_candidate
from mcmr.rules.general.deterministic.calls.r0001 import unchecked_result_call
from mcmr.rules.general.deterministic.calls.r0002 import unbounded_blocking_call
from mcmr.rules.general.deterministic.comments.r0005 import commented_out_code
from mcmr.rules.general.deterministic.functions.r0012 import cognitive_complexity
from mcmr.rules.general.deterministic.functions.r0013 import nesting_depth
from mcmr.rules.general.deterministic.functions.r0014 import required_parameter_count
from mcmr.rules.general.deterministic.parameters.r0001 import swappable_parameter_pair
from mcmr.rules.general.deterministic.parameters.r0002 import configuration_object_parameter

SPAN = SourceSpan(path="src/example.py")


def calls(*items: CallSite, language: str = "cuda") -> CallFact:
    """Build one resolved call index in the requested language."""
    return CallFact(key="calls", span=SPAN, calls=list(items), language=language)


def call(
    name: str,
    *,
    result_is_discarded: bool = False,
    keyword_names: tuple[str, ...] = (),
) -> CallSite:
    """Build one resolved call site."""
    return CallSite(
        qualified_name=name,
        path="src/kernel.cu",
        result_is_discarded=result_is_discarded,
        keyword_names=list(keyword_names),
    )


def test_cognitive_complexity_charges_nesting_but_not_sequence() -> None:
    """A structure inside another costs more than the same structures written in sequence."""
    nested = FunctionFact(
        key="function",
        span=SPAN,
        control_increments=[
            ControlIncrement(kind=ControlKind.LOOP),
            ControlIncrement(kind=ControlKind.CONDITIONAL, nesting_depth=1),
            ControlIncrement(kind=ControlKind.JUMP, nesting_depth=2),
        ],
    )
    sequential = nested.model_copy(
        update={
            "control_increments": [
                ControlIncrement(kind=ControlKind.LOOP),
                ControlIncrement(kind=ControlKind.CONDITIONAL),
            ]
        }
    )

    assert cognitive_complexity(nested) == 4
    assert cognitive_complexity(nested, nesting_penalty=2) == 5
    assert cognitive_complexity(sequential) == 2
    assert cognitive_complexity(FunctionFact(key="empty", span=SPAN)) == 0
    assert nesting_depth(nested) == 2
    assert nesting_depth(FunctionFact(key="empty", span=SPAN)) == 0


def test_required_parameter_count_ignores_receivers_and_defaults() -> None:
    """Only the inputs a caller has to decide on are counted."""
    subject = FunctionFact(
        key="function",
        span=SPAN,
        parameters=[
            FunctionParameter(name="self", is_receiver=True),
            FunctionParameter(name="template", is_required_by_external_contract=True),
            FunctionParameter(name="context", is_required_by_external_contract=True),
            FunctionParameter(name="encoding"),
        ],
    )

    assert required_parameter_count(subject).value == 2
    assert required_parameter_count(FunctionFact(key="empty", span=SPAN)).value == 0


def test_swappable_parameter_pair_needs_identical_adjacent_types() -> None:
    """Adjacent parameters of one type transpose silently, distinct types do not."""
    risky = FunctionFact(
        key="function",
        span=SPAN,
        parameters=[
            FunctionParameter(name="self", is_receiver=True),
            FunctionParameter(name="source", type_name="Path"),
            FunctionParameter(name="destination", type_name="Path"),
            FunctionParameter(name="overwrite", type_name="bool"),
        ],
    )
    typed = risky.model_copy(
        update={
            "parameters": [
                FunctionParameter(name="source", type_name="Source"),
                FunctionParameter(name="into", type_name="Sink"),
            ]
        }
    )
    untyped = risky.model_copy(
        update={
            "parameters": [
                FunctionParameter(name="left"),
                FunctionParameter(name="right"),
            ]
        }
    )

    assert swappable_parameter_pair(risky).value == 1
    assert swappable_parameter_pair(typed).value == 0
    assert swappable_parameter_pair(untyped).value == 0


def test_configuration_object_parameter_counts_attribute_only_inputs() -> None:
    """A parameter read only for its attributes should have been those attributes."""
    subject = ParameterFact(
        key="parameters",
        span=SPAN,
        parameters=[
            ParameterUse(annotation="Settings", attribute_reads=["host", "port"]),
            ParameterUse(annotation="Settings", attribute_reads=["host", "host"]),
            ParameterUse(
                annotation="Settings", attribute_reads=["host", "port"], operations=["iterate"]
            ),
            ParameterUse(
                annotation="Settings", attribute_reads=["host", "port"], all_uses_known=False
            ),
        ],
    )

    assert configuration_object_parameter(subject).value == 1
    assert configuration_object_parameter(subject, minimum_reads=1).value == 2


def test_value_dispatch_candidate_needs_one_subject_and_distinct_literals() -> None:
    """A chain that only maps one value to one arm is a lookup written as control flow."""

    def arm(literal: str, *, reads_subject_only: bool = True) -> ConditionalArm:
        return ConditionalArm(
            comparison="equals", literal=literal, reads_subject_only=reads_subject_only
        )

    dispatch = ConditionalChain(
        subject="kind",
        arms=[arm("pbs"), arm("slurm"), arm("ssh")],
        has_fallback=True,
    )
    mixed = dispatch.model_copy(
        update={"arms": [arm("pbs"), arm("slurm"), arm("ssh", reads_subject_only=False)]}
    )
    repeated = dispatch.model_copy(update={"arms": [arm("pbs"), arm("pbs"), arm("ssh")]})
    subject = BranchFact(key="branches", span=SPAN, chains=[dispatch, mixed, repeated])

    assert value_dispatch_candidate(subject) == 1
    assert value_dispatch_candidate(subject, minimum_arms=4) == 0


def test_unchecked_result_call_counts_only_configured_contracts() -> None:
    """A discarded status is a finding only where the project says the status matters."""
    subject = calls(
        call("cudaMalloc", result_is_discarded=True),
        call("cudaFree"),
        call("printf", result_is_discarded=True),
    )

    assert unchecked_result_call(subject, checked_prefixes=("cuda",)) == 1
    assert unchecked_result_call(subject, checked_callables=("cudaMalloc", "printf")) == 2
    assert unchecked_result_call(subject) == 0


def test_unbounded_blocking_call_reads_the_argument_names() -> None:
    """A configured blocking call needs one of the bound names among its arguments."""
    subject = calls(
        call("requests.get"),
        call("requests.get", keyword_names=("timeout",)),
        call("queue.get"),
        language="python",
    )

    assert unbounded_blocking_call(subject, bounded_callables=("requests.get",)) == 1
    assert (
        unbounded_blocking_call(
            subject, bounded_callables=("requests.get",), bound_names=("deadline",)
        )
        == 2
    )
    assert unbounded_blocking_call(subject) == 0


def test_commented_out_code_excludes_directives_and_prose() -> None:
    """A comment that parses as source is dead code unless it is a tool directive."""
    subject = CommentFact(
        key="comments",
        span=SPAN,
        groups=[
            CommentGroup(line_count=3, character_count=60, token_count=12, parses_as_source=True),
            CommentGroup(
                line_count=1,
                character_count=20,
                token_count=4,
                parses_as_source=True,
                is_directive=True,
            ),
            CommentGroup(line_count=2, character_count=40, token_count=8),
        ],
    )

    assert commented_out_code(subject) == 1
    assert commented_out_code(subject, minimum_lines=4) == 0


def test_cuda_transfer_and_barrier_cases() -> None:
    """Blocking transfers matter once streams exist, and raw barriers always have a typed form."""
    streamed = calls(
        call("cudaStreamCreate"),
        call("cudaMemcpy"),
        call("cudaMemcpyAsync"),
        call("__syncthreads"),
        call("__shfl_down_sync"),
        call("cooperative_groups::this_thread_block"),
    )
    sequential = calls(call("cudaMemcpy"))

    assert synchronous_transfer_in_stream_scope(streamed) == 1
    assert synchronous_transfer_in_stream_scope(sequential) == 0
    assert raw_barrier_over_cooperative_groups(streamed) == 2


def test_a_launch_says_which_stream_it_runs_on() -> None:
    """A launch with no fourth argument takes the default stream and drains every overlap."""
    launch = KernelLaunchFact(
        key="launch:src/scale.cu:scale",
        span=SourceSpan(path="src/scale.cu"),
        kernel="scale",
        grid="grid",
        block="block",
        unit_uses_streams=True,
    )

    assert default_stream_kernel_launch(launch)
    assert default_stream_kernel_launch(launch.model_copy(update={"stream": "0"}))
    assert not default_stream_kernel_launch(launch.model_copy(update={"stream": "stream"}))


def test_a_launch_where_no_stream_exists_has_no_overlap_to_drain() -> None:
    """The rule's own documented exception, which is a unit that never meets a stream at all."""
    launch = KernelLaunchFact(
        key="launch:src/scale.cu:scale",
        span=SourceSpan(path="src/scale.cu"),
        kernel="scale",
        grid="grid",
        block="block",
    )

    assert not default_stream_kernel_launch(launch)
    assert default_stream_kernel_launch(launch.model_copy(update={"unit_uses_streams": True}))
