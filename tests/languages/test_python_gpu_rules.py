from typing import TYPE_CHECKING, cast

import pytest

from mcmr.domain.contracts import RuleContract
from mcmr.facts import CallFact, FunctionFact, SyntaxFact
from mcmr.plugins import RepositoryTables
from mcmr.rules.python import (
    blocking_raw_memory_operation_in_stream_scope,
    conditional_block_barrier,
    default_stream_numba_kernel_launch,
    device_wide_numba_synchronization_in_stream_scope,
    device_wide_synchronization_in_stream_scope,
    direct_cuda_core_lifecycle_construction,
    dynamic_kernel_array_shape,
    kernel_return_value,
    legacy_default_stream_launch,
    synchronous_transfer_in_numba_stream_scope,
    unguarded_grid_index,
)
from mcmr.table import AnalysisSession

if TYPE_CHECKING:
    from mcmr.query import RuleQuery


@pytest.fixture(scope="module")
def gpu_tables(tmp_path_factory: pytest.TempPathFactory) -> RepositoryTables:
    """Parse one Python corpus covering unsafe and accepted GPU API forms."""
    root = tmp_path_factory.mktemp("python-gpu-rules")
    (root / "gpu.py").write_text(
        """from cuda.bindings import driver, runtime
from cuda.core import Context, Device, LEGACY_DEFAULT_STREAM, LaunchConfig, Stream, launch
from numba import cuda, float32


@cuda.jit
def unsafe_kernel(values, width):
    position = cuda.grid(1)
    cuda.shared.array(width * 2, float32)
    return values[position]


@cuda.jit
def guarded_kernel(values, width):
    position = cuda.grid(1)
    if position < width:
        cuda.syncthreads()
        values[position] = 0
    return


@cuda.jit(device=True)
def device_function(value):
    return value


def numba_host(values):
    stream = cuda.stream()
    unsafe_kernel[1, 32](values, 32)
    guarded_kernel[1, 32, stream](values, 32)
    values.copy_to_host()
    values.copy_to_host(stream=stream)
    cuda.synchronize()
    stream.synchronize()
    mapping = {}
    mapping[1, 32](values)


def cuda_python_host(values):
    Context()
    Stream()
    device = Device()
    stream = device.create_stream()
    launch(LEGACY_DEFAULT_STREAM, LaunchConfig(grid=1, block=32), unsafe_kernel, values)
    launch(stream, LaunchConfig(grid=1, block=32), unsafe_kernel, values)
    runtime.cudaDeviceSynchronize()
    driver.cuCtxSynchronize()
    runtime.cudaMemcpy(values, values, 1, 0)
    driver.cuMemAlloc(1)
    runtime.cudaMemcpyAsync(values, values, 1, 0, stream.handle)
"""
    )
    session = AnalysisSession(
        root,
        suffixes=[".py"],
        typed_families=[CallFact, FunctionFact, SyntaxFact],
    )
    tables = RepositoryTables()
    tables.add(session.call_tables())
    tables.add(session.function_tables())
    tables.add(session.syntax_tables())
    return tables


def count(rule: RuleContract, tables: RepositoryTables) -> int:
    """Return the total count from one table-native GPU rule invocation."""
    query = cast("RuleQuery", rule.invoke(tables, settings={}, dependencies={}))
    value = query.values.collect().get_column("integer_value").drop_nulls().sum()
    if not isinstance(value, int):
        raise TypeError("a GPU rule returned no integer count")
    return value


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        (kernel_return_value, 1),
        (conditional_block_barrier, 1),
        (unguarded_grid_index, 1),
        (dynamic_kernel_array_shape, 1),
        (synchronous_transfer_in_numba_stream_scope, 1),
        (default_stream_numba_kernel_launch, 1),
        (device_wide_numba_synchronization_in_stream_scope, 1),
        (direct_cuda_core_lifecycle_construction, 2),
        (legacy_default_stream_launch, 1),
        (device_wide_synchronization_in_stream_scope, 2),
        (blocking_raw_memory_operation_in_stream_scope, 2),
    ],
)
def test_python_gpu_rule_cases(
    rule: RuleContract,
    expected: int,
    gpu_tables: RepositoryTables,
) -> None:
    """Each GPU rule distinguishes its unsafe form from the accepted neighboring form."""
    assert count(rule, gpu_tables) == expected
