from ..... import rule
from .....facts import CallFact
from .....models import Count


@rule
def unchecked_result_call(
    subject: CallFact,
    *,
    checked_callables: tuple[str, ...] = (),
    checked_prefixes: tuple[str, ...] = (),
) -> Count:
    """Count calls whose result reports failure and is discarded anyway.

    Definition
    ----------
    Report a resolved call to a configured callable, or to any callable under a configured prefix,
    whose returned value is discarded. These are the calls that report failure through their result
    rather than by raising, so discarding the result discards the only failure signal there is. The
    project names the callables because the contract lives in the library rather than in the
    syntax. A CUDA runtime entry point, a Go function returning an error, a Rust `#[must_use]`
    result, and a status-returning C API all have this shape.

    Evidence
    --------
    Each finding records the call range and the qualified name. The value is the number of
    discarded results.

    Exceptions
    ----------
    A call whose value is assigned, returned, or passed onward is not counted, even when the
    receiving code ignores it later, because that is a separate question about the receiver. With
    no configured names the rule reports nothing, since guessing which results matter would produce
    findings a project never asked for. `checked_callables` names the exact callables whose result
    reports failure and `checked_prefixes` names the families of them, so a project states its own
    contract rather than inheriting a guess.

    Examples
    --------
    With `cuda*` configured, a bare `cudaMalloc(&pointer, bytes);` returns `1` while
    `status = cudaMalloc(&pointer, bytes);` returns `0`.

    References
    ----------
    Cites "CUDA C++ Best Practices Guide", error handling
    https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html#error-handling
    Generalizes clang-tidy bugprone-unused-return-value
    https://clang.llvm.org/extra/clang-tidy/checks/bugprone/unused-return-value.html
    Cites "The Rust Reference", `#[must_use]` attribute
    https://doc.rust-lang.org/reference/attributes/diagnostics.html#the-must_use-attribute
    """
    return sum(
        call.result_is_discarded
        and (
            call.qualified_name in checked_callables
            or call.qualified_name.startswith(checked_prefixes)
        )
        for call in subject.calls
    )
