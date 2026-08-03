# Python GPU API inventory

MCMR treats Numba CUDA and CUDA Python as Python API domains. Their code is discovered as Python,
then the rules join call, function, and syntax tables produced by the same Rust kernel pass as the
rest of the catalog. This avoids the old mistake of limiting CUDA analysis to `.cu` and `.cuh`
files when the launch and ownership policy is written in Python.

The inventory was checked against the current NVIDIA documentation on 2026-08-02. Numba CUDA is in
maintenance mode through CUDA 13, but existing projects still need precise checks while new feature
development moves toward Numba-CUDA-MLIR.

## Implemented Numba CUDA rules

| Rule | Question answered | Typed evidence |
| --- | --- | --- |
| `PY-NUMB0001` | Does a kernel return a value to its host caller | `SyntaxFact` joined with `FunctionFact` decorators |
| `PY-NUMB0002` | Is a block barrier nested in divergent control flow | syntax subtree intervals inside decorated kernels |
| `PY-NUMB0003` | Is a grid index never read by bounded control flow | binding, call, name, branch, and loop syntax relations |
| `PY-NUMB0004` | Does a local or shared array shape depend on a kernel parameter | call expressions joined with kernel parameters and source bounds |
| `PY-NUMB0005` | Does a transfer omit the stream used by its module | resolved calls, positional arguments, and keywords |
| `PY-NUMB0006` | Does a real decorated kernel launch omit its stream | call, index, collection, decorator, and module stream relations |
| `PY-NUMB0007` | Does a stream-using module wait for every device stream | resolved stream creation and `cuda.synchronize` calls |

## Implemented CUDA Python rules

| Rule | Question answered | Typed evidence |
| --- | --- | --- |
| `PY-CUDA0001` | Are `cuda.core` stream or context wrappers constructed through an unsupported owner boundary | resolved constructor calls |
| `PY-CUDA0002` | Does `cuda.core.launch` use the legacy default stream | the resolved launch and its first argument expression |
| `PY-CUDA0003` | Does a stream-using module call a device-wide runtime or driver barrier | resolved core, runtime, and driver calls |
| `PY-CUDA0004` | Does a stream-using module allocate, copy, clear, or free memory through a blocking raw API | an explicit inventory of synchronous driver and runtime memory calls |

The shared design principles are explicit streams, synchronization at the narrowest dependency,
compile-time kernel-local storage shapes, and bounds before indexing a rounded launch grid. These
are the CUDA C++ practices whose evidence survives the Python API boundary.

## Deliberately deferred checks

Some useful checks cannot yet be stated honestly from the available evidence.

| Candidate | Missing evidence |
| --- | --- |
| Implicit host transfer when a NumPy array is passed to a kernel | inferred host and device buffer types at each launch argument |
| Debug kernels retained in production | a declared build or deployment intent rather than a decorator alone |
| Deallocation that causes an implicit synchronization | Python lifetime, garbage collection, and buffer ownership facts |
| Copying through the CUDA Array Interface instead of direct interoperability | inferred array framework types and reaching definitions |
| Occupancy, register pressure, bank conflicts, and launch sizing | compiled kernel attributes or runtime profiler records |
| Migration from Numba CUDA to Numba-CUDA-MLIR | dependency lifecycle evidence rather than a local source verdict |

MCMR should add these only when a provider can supply the primitive evidence. Guessing from a
method name would recreate the provider verdict defect that the table migration removed.

## Primary references

- [Numba CUDA kernel guide](https://nvidia.github.io/numba-cuda/user/kernels.html)
- [Numba CUDA kernel API](https://nvidia.github.io/numba-cuda/reference/kernel.html)
- [Numba CUDA memory management](https://nvidia.github.io/numba-cuda/reference/memory.html)
- [CUDA Python core guide](https://nvidia.github.io/cuda-python/cuda-core/latest/10_minutes_to_cuda_core.html)
- [CUDA Python core API](https://nvidia.github.io/cuda-python/cuda-core/latest/api.html)
- [CUDA Python runtime bindings](https://nvidia.github.io/cuda-python/cuda-bindings/latest/module/runtime.html)
