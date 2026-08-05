from pathlib import Path
from typing import TYPE_CHECKING, cast

from mcmr.domain.contracts import FixSafety, RuleContract, RuleSetting, RuleValue
from mcmr.facts import (
    BranchFact,
    CallFact,
    CommentFact,
    CommentGroup,
    ConditionalArm,
    ConditionalChain,
    FunctionFact,
    KernelLaunchFact,
    NodeRef,
    ParameterFact,
    ParameterUse,
    SourceSpan,
)
from mcmr.query import RuleQuery, scalar_frame_value
from mcmr.rules.cuda import (
    default_stream_kernel_launch,
    raw_barrier_over_cooperative_groups,
    synchronous_transfer_in_stream_scope,
)
from mcmr.rules.general import (
    cognitive_complexity,
    commented_out_code,
    configuration_object_parameter,
    nesting_depth,
    required_parameter_count,
    swappable_parameter_pair,
    unbounded_blocking_call,
    unchecked_result_call,
    value_dispatch_candidate,
)
from mcmr.table import AnalysisSession, FunctionRelation

from ..support import retained_query

if TYPE_CHECKING:
    from mcmr.plugins import Fact, Table

_SPAN = SourceSpan(path="src/example.py")


def native_query(
    table: Table[Fact],
    rule: RuleContract,
    **settings: RuleSetting,
) -> RuleQuery:
    """Invoke one specialized expansion rule once over its repository table."""
    result = rule.invoke_table(table, settings=settings, dependencies={})
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic expansion rule returned a model query")
    return result


def scalar(query: RuleQuery, fact_id: str | None = None) -> RuleValue:
    """Return one scalar from a generic row or selected specialized row."""
    values = query.values.collect()
    if fact_id is not None:
        values = values.filter(values["fact_id"] == fact_id)
    return scalar_frame_value(values)


def function_id(table: Table[Fact], name: str) -> str:
    """Return the stable fact identity of one named function row."""
    functions = table.frame(FunctionRelation.FUNCTIONS)
    identity = functions.filter(functions["name"] == name).item(0, "fact_id")
    if not isinstance(identity, str):
        raise TypeError("a function row has no string identity")
    return identity


def function_table(root: Path, source: str) -> Table[Fact]:
    """Parse one Python source fixture into native function relations."""
    (root / "subject.py").write_text(source, encoding="utf-8")
    return cast(
        "Table[Fact]",
        AnalysisSession(
            root,
            suffixes=(".py",),
            typed_families=(FunctionFact,),
        ).function_tables(),
    )


def call_table(root: Path, name: str, *, source: str) -> Table[Fact]:
    """Parse one source fixture into native resolved-call relations."""
    (root / name).write_text(source, encoding="utf-8")
    return cast(
        "Table[Fact]",
        AnalysisSession(
            root,
            suffixes=(Path(name).suffix,),
            typed_families=(CallFact,),
        ).call_tables(),
    )


def test_cognitive_complexity_charges_nesting_but_not_sequence(tmp_path: Path) -> None:
    """A structure inside another costs more than the same structures written in sequence."""
    table = function_table(
        tmp_path,
        """def nested(items):
    found = None
    for item in items:
        if item:
            found = item
            break
    return found

def sequential(items):
    for item in items:
        print(item)
    if items:
        print(items)

def empty():
    return None
""",
    )
    complexity = native_query(table, cognitive_complexity)
    penalized = native_query(table, cognitive_complexity, nesting_penalty=2)
    depth = native_query(table, nesting_depth)

    assert scalar(complexity, function_id(table, "nested")) == 4
    assert scalar(penalized, function_id(table, "nested")) == 5
    assert scalar(complexity, function_id(table, "sequential")) == 2
    assert scalar(complexity, function_id(table, "empty")) == 0
    assert scalar(depth, function_id(table, "nested")) == 2
    assert scalar(depth, function_id(table, "empty")) == 0


def test_required_parameter_count_ignores_receivers_and_defaults(tmp_path: Path) -> None:
    """Only the inputs a caller has to decide on are counted."""
    table = function_table(
        tmp_path,
        """class Renderer:
    def render(self, template, context, encoding='utf-8'):
        return template.format(**context).encode(encoding)

def empty():
    return None
""",
    )
    query = native_query(table, required_parameter_count)

    assert scalar(query, function_id(table, "render")) == 2
    assert scalar(query, function_id(table, "empty")) == 0


def test_swappable_parameter_pair_needs_identical_adjacent_types(tmp_path: Path) -> None:
    """Adjacent parameters of one type transpose silently, distinct types do not."""
    table = function_table(
        tmp_path,
        """from pathlib import Path

class Copier:
    def risky(self, source: Path, destination: Path, overwrite: bool):
        return source, destination, overwrite

def typed(source: str, into: bytes):
    return source, into

def untyped(left, right):
    return left, right
""",
    )
    query = native_query(table, swappable_parameter_pair)

    assert scalar(query, function_id(table, "risky")) == 1
    assert scalar(query, function_id(table, "typed")) == 0
    assert scalar(query, function_id(table, "untyped")) == 0


def test_configuration_object_parameter_counts_attribute_only_inputs() -> None:
    """A parameter read only for its attributes should have been those attributes."""
    subject = ParameterFact(
        key="parameters",
        span=_SPAN,
        parameters=[
            ParameterUse(annotation="Settings", attribute_reads=["host", "port"]),
            ParameterUse(annotation="Settings", attribute_reads=["host", "host"]),
            ParameterUse(annotation="SourceSpan", attribute_reads=["path", "start_line"]),
            ParameterUse(annotation="Profile", attribute_reads=["name", "strictness"]),
            ParameterUse(
                annotation="Settings", attribute_reads=["host", "port"], operations=["iterate"]
            ),
            ParameterUse(
                annotation="Settings", attribute_reads=["host", "port"], all_uses_known=False
            ),
        ],
    )

    assert scalar(retained_query(subject, configuration_object_parameter)) == 1
    assert scalar(retained_query(subject, configuration_object_parameter, minimum_reads=1)) == 2
    assert (
        scalar(
            retained_query(
                subject,
                configuration_object_parameter,
                configuration_markers=["profile"],
            )
        )
        == 1
    )


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
        node=NodeRef(id="dispatch", span=_SPAN),
    )
    mixed = dispatch.model_copy(
        update={"arms": [arm("pbs"), arm("slurm"), arm("ssh", reads_subject_only=False)]}
    )
    repeated = dispatch.model_copy(update={"arms": [arm("pbs"), arm("pbs"), arm("ssh")]})
    subject = BranchFact(key="branches", span=_SPAN, chains=[dispatch, mixed, repeated])

    assert scalar(retained_query(subject, value_dispatch_candidate)) == 1
    assert scalar(retained_query(subject, value_dispatch_candidate, minimum_arms=4)) == 0


def test_unchecked_result_call_counts_only_configured_contracts(tmp_path: Path) -> None:
    """A discarded status is a finding only where the project says the status matters."""
    table = call_table(
        tmp_path,
        "kernel.cu",
        source="""void run(void **pointer) {
    cudaMalloc(pointer, 4);
    auto released = cudaFree(*pointer);
    printf("done");
}
""",
    )

    assert scalar(native_query(table, unchecked_result_call, checked_prefixes=["cuda"])) == 1
    assert (
        scalar(
            native_query(
                table,
                unchecked_result_call,
                checked_callables=["cudaMalloc", "printf"],
            )
        )
        == 2
    )
    assert scalar(native_query(table, unchecked_result_call)) == 0


def test_unbounded_blocking_call_reads_the_argument_names(tmp_path: Path) -> None:
    """A configured blocking call needs one of the bound names among its arguments."""
    table = call_table(
        tmp_path,
        "client.py",
        source="""import queue
import requests

def fetch(url):
    first = requests.get(url)
    second = requests.get(url, timeout=3)
    third = queue.get()
    return first, second, third
""",
    )

    assert (
        scalar(native_query(table, unbounded_blocking_call, bounded_callables=["requests.get"]))
        == 1
    )
    assert (
        scalar(
            native_query(
                table,
                unbounded_blocking_call,
                bounded_callables=["requests.get"],
                bound_names=["deadline"],
            )
        )
        == 2
    )
    assert scalar(native_query(table, unbounded_blocking_call)) == 0


def test_commented_out_code_excludes_directives_and_prose() -> None:
    """A comment that parses as source is dead code unless it is a tool directive."""
    subject = CommentFact(
        key="comments",
        span=_SPAN,
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

    answer = retained_query(subject, commented_out_code)
    assert scalar(answer) == 1
    assert answer.findings is not None
    findings = answer.findings.rows.collect()
    assert (
        findings.item(0, "message"),
        findings.item(0, "path"),
        dict(
            zip(
                findings.item(0, "measurement_names"),
                findings.item(0, "measurement_values"),
                strict=True,
            )
        ),
    ) == (
        "this 3-line comment group parses as source rather than prose",
        _SPAN.path,
        {
            "lines in the comment group": 3,
            "characters in the comment group": 60,
            "tokens in the comment group": 12,
        },
    )
    assert answer.fix is not None
    assert (
        answer.fix.summary,
        commented_out_code.query_fix_safety,
        answer.fix.rewrites.collect().is_empty(),
    ) == (
        "Delete each run of commented lines that is source rather than prose.",
        FixSafety.REVIEW,
        True,
    )
    assert scalar(retained_query(subject, commented_out_code, minimum_lines=4)) == 0


def test_cuda_transfer_and_barrier_cases(tmp_path: Path) -> None:
    """Blocking transfers matter once streams exist, and raw barriers always have a typed form."""
    (tmp_path / "sequential.cu").write_text(
        """void sequential(void *target, void *source) {
    cudaMemcpy(target, source, 4, cudaMemcpyDeviceToDevice);
}
""",
        encoding="utf-8",
    )
    table = call_table(
        tmp_path,
        "kernel.cu",
        source="""void streamed(void *target, void *source, cudaStream_t *stream) {
    cudaStreamCreate(stream);
    cudaMemcpy(target, source, 4, cudaMemcpyDeviceToDevice);
    cudaMemcpyAsync(target, source, 4, cudaMemcpyDeviceToDevice, *stream);
    __syncthreads();
    __shfl_down_sync(0xffffffff, 1, 1);
    cooperative_groups::this_thread_block();
}
""",
    )

    transfers = native_query(table, synchronous_transfer_in_stream_scope)
    barriers = native_query(table, raw_barrier_over_cooperative_groups)
    transfer_values = transfers.values.collect()
    assert dict(
        zip(
            transfer_values.get_column("path"),
            transfer_values.get_column("integer_value"),
            strict=True,
        )
    ) == {"kernel.cu": 1, "sequential.cu": 0}
    assert barriers.values.collect().get_column("integer_value").sum() == 2


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

    assert scalar(retained_query(launch, default_stream_kernel_launch)) is True
    assert (
        scalar(
            retained_query(launch.model_copy(update={"stream": "0"}), default_stream_kernel_launch)
        )
        is True
    )
    assert (
        scalar(
            retained_query(
                launch.model_copy(update={"stream": "stream"}), default_stream_kernel_launch
            )
        )
        is False
    )


def test_a_launch_where_no_stream_exists_has_no_overlap_to_drain() -> None:
    """The rule's own documented exception, which is a unit that never meets a stream at all."""
    launch = KernelLaunchFact(
        key="launch:src/scale.cu:scale",
        span=SourceSpan(path="src/scale.cu"),
        kernel="scale",
        grid="grid",
        block="block",
    )

    assert scalar(retained_query(launch, default_stream_kernel_launch)) is False
    assert (
        scalar(
            retained_query(
                launch.model_copy(update={"unit_uses_streams": True}),
                default_stream_kernel_launch,
            )
        )
        is True
    )
