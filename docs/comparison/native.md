# MCMR against the C, C++, and CUDA tools

What MCMR is for, where it deliberately does not compete, and what a measurement over real native
code says about both. Everything numbered here was run on this machine on 2026-07-27 unless the
line says it comes from documentation.

Formatting is out of scope. MCMR does not format and never will, so clang-format is not a
comparison, and the parts of cpplint and of the readability group that are about braces, line
length, and spacing are noted only where they inflate a count.

## What MCMR is for

MCMR judges a repository against the engineering policy a project chose. A rule reads one typed
fact, returns an occurrence, a count, a percentage, or a category, and its own acceptance contract
decides what that observation is worth. It reads six languages through one fact contract, and reads git history and
the whole module graph rather than one file.

It does not compete on local correctness, memory safety, or undefined behavior in C, C++, or CUDA,
and this document argues that it should not start.

## The dividing line, stated first because it decides everything else

clang-tidy runs inside Clang. It receives a fully preprocessed, fully type-checked translation unit
built from a real compilation database, with every macro expanded, every template instantiated,
every include resolved, and every expression carrying its type. On top of that the Clang Static
Analyzer walks paths through the function with symbolic values.

MCMR reads tree-sitter parses of individual files. There is no preprocessor, no include resolution,
no type checking, and no instantiation. That is a very large disadvantage and it is not a detail at
the edges. It means MCMR cannot see, in principle rather than for want of a rule.

* Anything behind a macro. A function defined by a function-like macro does not exist for MCMR at
  all, and a bug in a macro argument that the expansion evaluates twice is invisible.
* Anything a template instantiation produces. A body that is correct for one instantiation and
  wrong for another is one body to MCMR.
* Whether a name is a type. C++ cannot be parsed without a symbol table, so `a<b>c` and the most
  vexing parse are both ambiguous to a grammar-only reader, and tree-sitter recovers rather than
  resolves.
* The real type of an expression, including the type of a parameter. This one is measured below
  and it costs a real rule a real fraction of its findings.
* Which branch is reachable. `#if`, `#ifdef`, and configuration macros select code, and MCMR reads
  whatever the grammar accepts without knowing which arm the build compiles.
* Anything the linker or the whole program knows, and anything that needs runtime.

Here is that as a table, because it is the axis every other axis reduces to.

| Evidence | clang-tidy and the Clang Static Analyzer | cppcheck | GCC and Clang warnings | compute-sanitizer | MCMR |
|---|---|---|---|---|---|
| Preprocessed source | yes | yes, its own preprocessor over every configuration | yes | not applicable | **no** |
| Type information | full, from Sema | partial, its own value-flow types | full | not applicable | parameter and return type spelled as written, with the declarator dropped |
| Template instantiation | yes | no | yes | not applicable | no |
| Dataflow inside a function | yes | yes | yes, `-fanalyzer` | not applicable | no |
| Path sensitivity | yes, the static analyzer | yes, value flow | `-fanalyzer` | not applicable | no |
| Whole translation unit | yes | yes | yes | not applicable | no, one file at a time |
| Whole program | no, one TU at a time | `--enable=unusedFunction` across a project | link-time only | yes at runtime | yes, a repository graph |
| Include and macro graph | yes | yes | yes | not applicable | `#include` lines only, unresolved |
| Runtime behavior | no | no | no | yes | no |
| Git history | no | no | no | no | yes |
| Cross-language references | no | no | no | no | yes, lexically |
| Needs a build to say anything | yes, a compilation database | no | yes | yes, a running binary | no |

The last row is the one place the sign flips, and it is the whole of MCMR's honest claim here.

## What MCMR's catalog actually holds for these languages

The catalog is 275 rules. By scope, read out of the catalog rather than from memory.

| Scope | Rules |
|---|---|
| general | 151 |
| python | 111 |
| rust | 5 |
| typescript | 4 |
| cuda | 3 |
| **cpp** | **0** |
| **c** | **0** |

There is no C-scoped or C++-scoped rule in MCMR. Everything MCMR says about C and C++ is a general
rule that happens to run, plus three CUDA rules. Those three are `CU-LAUN0001` raw barriers and
warp intrinsics where Cooperative Groups exists, `CU-LAUN0002` a launch with no stream, and
`CU-MEMO0001` a blocking transfer in a translation unit that also creates a stream.

`general` does not mean the rule fires. A rule runs only when the kernel fills the fact family it
reads, and the native frontend fills far fewer families than the Python one.
`tests/test_language_coverage.py` records nine families a general rule reads that no native
frontend answers, each with a written reason. Building every family over the tokenization corpus
finds ten empty, which is those nine plus one the guard cannot see, and this is what they cost.

| Empty family | General deterministic rules blinded |
|---|---|
| `OverrideFact` | 11 |
| `ProseSegmentFact` | 3 |
| `StringExpressionFact` | 2 |
| `AttributeAccessFact`, `BranchFact`, `DependencyComponentFact`, `LiteralGroupFact`, `MethodGroupFact`, `ParameterFact`, `WaiverFact` | 1 each |

`OverrideFact` is the expensive one. Eleven general rules about overriding, signature drift, and
inheritance depth read it, and it is empty for every native corpus measured here. It is also not in
the coverage test's gap table, because the language-coverage fixture states no inheritance, so the
reference frontend never answers it either and the comparison never reaches it. That is a hole the
guard cannot see.

The other structural gap is discovery. The kernel's default suffix list holds `.c`, `.h`, `.cc`,
`.cpp`, `.cxx`, `.hpp`, `.hh`, `.cu`, and `.cuh`, and does not hold `.inl`, `.ipp`, `.tpp`, or
`.hxx`. On cuCollections that is 26 `.inl` files and 13,751 lines out of 76,583, which is 18 percent of
the library and the part holding the implementations, silently absent from every count MCMR
prints.

## The corpora, and what MCMR finds on them

Three real native repositories. Nobody wrote any of them to be measured.

| Corpus | Files MCMR reads | Lines | What it is |
|---|---|---|---|
| `research/projects/tokenization` | 33 | 3,781 | first-party CUDA and C++ behind nanobind, built by CMake |
| `research/projects/llm-head` | 29 | 11,857 | a CAGRA port, 27 of 29 files are `.cuh` headers, compiled at runtime by CuPy |
| cuCollections, vendored under tokenization | 206 | 62,832 | NVIDIA's own header-only CUDA container library |

How much of the catalog runs.

| Corpus | Rules selected | Made any observation | A policy could judge | Reported anything |
|---|---|---|---|---|
| tokenization | 279 | 72 | 69 | 25 |
| llm-head | 279 | 83 | 80 | 24 |
| cuCollections | 279 | 72 | 69 | 35 |

So roughly a quarter of the catalog sees evidence on a native repository and a tenth of it says
anything. Of the 25 rules that reported on tokenization, three are the CUDA rules, one is
`PY-TYPE0003` firing on a manifest, and two are history and lifecycle rules about the repository
rather than about the code. About twenty rules judge the native source itself.

That is the honest headline, and it should be read beside the standing caveat that a recent audit
found 43 deterministic rules that see evidence and never fire on four large real corpora. The
figures above corroborate it from the other direction. On tokenization 43 rules observed evidence
and reported nothing, on llm-head 55, on cuCollections 33.

### What the twenty rules find

Concentrated, and the concentration is the problem. The counts below are failing observations, one
per record the rule judged, which for a function-level rule is one per function. `mcmr check`
prints more lines than that, because a rule that names several sites inside one function prints one
line each, and the two units are kept apart wherever both appear below.

| Rule | tokenization | llm-head | cuCollections |
|---|---|---|---|
| `ALL-PARA0001` swappable parameter pair | 95 | 126 | 111 |
| `ALL-DUPL0003` pasted block copy | 57 | 140 | 504 |
| `ALL-FUNC0010` required parameter count | 40 | 57 | 52 |
| `ALL-FUNC0006` shallow callable | 12 | 33 | 193 |
| `ALL-COMM0001` comment length | 1 | 7 | 206 |
| `ALL-REAC0001` and `ALL-REAC0002` reach | 30 | 39 | 130 |
| `CU-LAUN0002` default stream launch | 12 | 0 | 51 |
| `CU-LAUN0001` raw barrier | 5 | 12 | 4 |
| `CU-MEMO0001` blocking transfer in stream scope | 1 | 0 | 0 |
| everything else together | 82 | 219 | 298 |
| **total failing sites** | **335** | **633** | **1,549** |

Two of those numbers are worth stopping on.

`ALL-COMM0001` fires on 206 of cuCollections' 206 files. Every NVIDIA source opens with the
fifteen-line Apache-2.0 notice, the rule measures the longest contiguous comment group normalized
against 200 tokens, and the then-current default policy failed anything past 40 percent. A rule with a 100
percent fire rate has told the reader nothing. The rule's own documentation anticipates this and
says a legal notice measures exactly as long as it is, and the configured policy failed it anyway.

`ALL-PARA0001` prints 282 of the 613 lines the tokenization run produced, which is 46 percent of
everything a reader sees, and it is measurably wrong a fifth of the time. The native frontend reads
a parameter's `type_name` from the tree-sitter `type` field alone, which drops the pointer
declarator and the `const` qualifier, so `int32_t *__restrict__ tokens` and `int32_t seg_start`
both arrive as `int32_t`. Re-reading the signature behind every one of those lines out of the
source gives this.

| Of the 277 `ALL-PARA0001` lines whose signature could be re-read | Count | Share |
|---|---|---|
| both parameters really share their full declared type | 216 | 78% |
| shape differs, one is a value and the other a pointer, so no caller can transpose them | 37 | 13% |
| only constness differs, so the transposition compiles in one direction only | 24 | 9% |

Thirteen percent are findings a compiler would refuse to accept as a mistake, and another nine
percent are half-real. clang-tidy's `bugprone-easily-swappable-parameters` answers the same
question from the real type and reports `int32_t *__restrict` as its own type, so it does not make
either error.

## The C and C++ tools

### clang-tidy

Version 22.1.8 here. `clang-tidy --list-checks -checks='*'` prints **604 checks**. The groups the
brief asks about.

| Group | Checks |
|---|---|
| `bugprone` | 103 |
| `readability` | 57 |
| `modernize` | 46 |
| `cppcoreguidelines` | 42 |
| `cert` | 41 |
| `misc` | 27 |
| `performance` | 19 |
| `portability` | 5 |
| `concurrency` | 2 |
| `clang-analyzer` | 128 |
| `hicpp` | 31 |
| everything else, including Abseil, Android, Fuchsia, Google, LLVM, Objective-C, Altera, MPI, OpenMP | 103 |

A check-count comparison against MCMR's 279 would be close to meaningless, so here is the
comparison that is not. Over the tokenization block module, 14 translation units through a
compilation database, `bugprone-*` through `readability-*` plus `clang-analyzer-*`, restricted to
first-party files and deduplicated by file, line, column, and check, clang-tidy reports **489
findings across 34 distinct checks**. MCMR over the same subtree reports **256 findings across 17
rules**, 149 of which are the one rule above.

Where the two overlap, clang-tidy is deeper on its own ground.

| Question | clang-tidy | MCMR |
|---|---|---|
| adjacent parameters a caller can transpose | 34, from the real type, grouped as runs of N | 149, from the spelled type, one per pair, 22 percent unsound |
| a declaration that could be internal | 63 `misc-use-internal-linkage`, from linkage | 30 `ALL-REAC0001` and `ALL-REAC0002`, from a lexical reach graph |
| pointer arithmetic on a raw pointer | 115 | none, no rule |
| a parameter copied when a reference would do | 22 `performance-unnecessary-value-param` | none, on the backlog as item 4 |
| a member function that never mutates | 5 `misc-const-correctness` | none, on the backlog as item 22 |
| an include nothing in the file needs | 16 `misc-include-cleaner` | none, no general rule reads `ImportBindingFact` |
| the rule of five | `cppcoreguidelines-special-member-functions` | none, on the backlog as item 21 |

The last three rows are the ones MCMR's backlog already promises, and clang-tidy ships all of them
with the type system behind them.

### The Clang Static Analyzer

128 checks reached through clang-tidy as `clang-analyzer-*`, or standalone through `scan-build` and
`CodeChecker`. It is a path-sensitive symbolic execution engine, which is a different kind of
machine from everything else in this document. On a four-line demonstration it reports the
`strcpy` into a buffer sized by `strlen` without the terminator, with the path that reaches it.
MCMR has no path sensitivity and cannot acquire it from a tree-sitter parse.

### cppcheck

2.17.1 here. `cppcheck --errorlist` prints **320 error identifiers**, split 85 error, 106 warning,
90 style, 18 portability, 15 performance, 6 information. A default run reports "Active checkers
167/856", so most of the engine sits behind `--check-level=exhaustive` or behind Cppcheck Premium.

cppcheck does not need a compilation database, which makes it the closest incumbent to MCMR's
posture, and it is genuinely good at C. It is also **the clearest demonstration in this document
of what happens when a tool meets CUDA without a CUDA parser**. Forced to read the tokenization
block module as C++, it reported this.

```
impl.cuh:88:43: error: Shifting 32-bit value by 256 bits is undefined behaviour [shiftTooManyBits]
```

Line 88 is `classify_segments_kernel<<<blocks, 256>>>(...)`. It parsed the launch bracket as a chain
of shifts. Three such errors, all confidently wrong. It also reported four `__global__` kernels as
"never used", because a launch is not a call it recognizes. Total useful output on the block
module's 23 files and 1,463 lines of CUDA, close to zero, in 0.43 seconds.

MCMR is better than cppcheck on CUDA source, and that is a real result rather than a rhetorical
one. MCMR uses `tree-sitter-cuda` for `.cu` and `.cuh`, so `__global__` is a node and
`scale<<<grid, block, 0, stream>>>(data)` arrives as a call carrying its execution configuration.

### include-what-you-use

Not installed here, so this is from documentation. Version 0.26 was released in March 2026 against
Clang 22, so the project is current. It is a Clang tool, it needs the same compilation database
clang-tidy needs, and it answers a question MCMR has no rule for at all. clang-tidy's
`misc-include-cleaner` now covers much of the same ground inside clang-tidy, and reported 16
first-party findings on the block module.

### Facebook Infer

Not run here. From documentation, it analyzes C, C++, and Objective-C through a Clang frontend,
runs an interprocedural separation-logic analysis, and needs a real build command such as
`infer run -- make`. Its strength is interprocedural memory safety and its published C++ support
has always been narrower than its Java support. It is the only free tool in this list doing
interprocedural reasoning of that kind. MCMR does interprocedural work only at the level of the
import and reach graph, never at the level of values.

### PVS-Studio

Commercial, free for open source under a comment-header scheme. C, C++, C#, and Java. I found no
documented support for `.cu` and could not verify one, so treat CUDA as unsupported until somebody
checks. Its published strength is a very large rule set with strong null and copy-paste diagnostics
and a well-run false-positive process.

### Coverity

Commercial, now sold by Black Duck. Coverity Scan is free for open source and is the
practical way most projects meet it. Its documentation claims coverage of NVIDIA's CUDA C++
guidelines, which if accurate would make it the only commercial static analyzer in this list with
a stated CUDA position. Unverified here. Its model is a build capture followed by an
interprocedural whole-program analysis, so it needs everything a compilation database needs and
more.

### MISRA and AUTOSAR

The cppcheck MISRA addon ships in the wheel and works. It implements **131 MISRA C 2012 rules**. It
produced six violations on a three-line C file. It also demonstrates the barrier, since the rule
texts are copyrighted and the addon prints only identifiers until the user supplies
`--rule-texts` extracted from a purchased copy of the standard.

```
[misra.c:2] (style) misra violation (use --rule-texts=<file> to get proper output) [misra-c2012-15.5]
```

For MISRA C++ 2023 and AUTOSAR C++14 the free options thin out fast. clang-tidy's `cert-*` and
`hicpp-*` groups overlap parts of AUTOSAR, and complete coverage is Cppcheck Premium, Helix QAC,
LDRA, Parasoft, or PVS-Studio. MCMR has no position here and should not acquire one. A certified
tool qualification package is the product, not the checks.

### GCC and Clang warning sets

GCC 13.3.0 here. `gcc --help=warnings` lists **425 warning flags**, of which **46** are
`-Wanalyzer-*`. `-fanalyzer` works for C++ in this release and reported
`-Wanalyzer-possible-null-argument` on the demonstration file. This is table stakes and it is free,
and no project should reach for anything else before turning it on.

On the tokenization CUDA translation unit, compiled with the third-party trees under `-isystem` and
`-Wall -Wextra`, nvcc and its host GCC reported **zero** warnings. Adding `-Wpedantic` produced 617
first-party warnings, every one of them "style of line directive is a GCC extension", which is an
artifact of nvcc's own generated `#line` directives. So on CUDA, `-Wpedantic` is noise and
`-Wall -Wextra` is quiet, which means everything MCMR and clang-tidy report on this corpus is above
the compiler's bar rather than duplicating it.

### lizard

1.23.0 here, and it has a trap. Pointed at a directory it analyzed **one file** of the block
module, `module.cpp`, because its directory walk does not treat `.cu` and `.cuh` as C++. Named
explicitly, `lizard kernel.cuh` works and reports NLOC 74, CCN 9. So lizard on a CUDA project
silently measures almost nothing unless every file is listed by hand. MCMR's `ALL-FUNC0001`,
`ALL-FUNC0008`, and `ALL-CONT0004` answer the same family of questions and do read `.cu` and
`.cuh`.

### cpplint

2.0.2 here. 296 findings on the block module in 0.34 seconds, of which **246 are
`whitespace/line_length`**, 23 `legal/copyright`, and 21 `build/include_order`. It is a Google
style guide checker and most of what it says is formatting, which is out of scope. Its
`build/include_order` and `build/include_what_you_use` checks are the only parts that judge
something MCMR could care about.

### flawfinder

2.0.20 here, **72 rules**, all of them a lexical match against a list of dangerous C library
functions. Pointed at the block module it analyzed **23 lines** in one file, because it too skips
`.cu` and `.cuh` in a directory walk. On the demonstration file it correctly reported `strcpy`
CWE-120 and `strlen` CWE-126, which is exactly its job and the whole of it. It is a grep with a
good list. MCMR's `ALL-SECU` family occupies the same lexical tier and is broader in intent.

### Tools in real use that the brief did not name

* **CodeChecker**, Ericsson's wrapper around the Clang Static Analyzer and clang-tidy, which adds
  a database, a web UI, baselining, and suppression management. It is how most large C++ shops
  actually run the analyzer, and it is on PyPI.
* **sparse** and **smatch**, the Linux kernel's own checkers, and **Coccinelle**, which does
  semantic patching. Real, in daily use, and C-only.
* **Frama-C** and **CBMC**, deductive verification and bounded model checking for C. Different
  category, used where correctness is contractual.
* **Clang thread safety analysis**, `-Wthread-safety`, annotation-driven and effectively free.
* **The sanitizers**, ASan, UBSan, TSan, MSan, and **Valgrind**. Runtime, and the actual answer to
  memory safety in C and C++. Nothing static in this list replaces them.
* **clazy** for Qt, **SonarQube** and **Semgrep** for the cross-language tier, both of which belong
  to another comparison.
* **OCLint** is at 22.02 with only minor repository activity since, so treat it as dormant rather
  than as a live option. It is named here rather than dropped silently.

## The CUDA tools

### compute-sanitizer

2026.2.1.0 here, four tools, all **runtime**. On a deliberately racy reduction it produced this in
0.87 seconds.

```
Error: Race reported between Write access at reduce(const float *, float *)+0x70 in race.cu:5
    and Read access at reduce(const float *, float *)+0x90 in race.cu:9 [12 hazards]
```

`initcheck` separately reported the uninitialized global read, with the thread and block that did
it. MCMR ran on the same file and reported the `printf`, a two-character local name, and a
swappable pair that is not swappable, and said nothing about the missing `__syncthreads()`.

That is the correct division. compute-sanitizer needs a built binary, a GPU, and an input that
reaches the code. MCMR needs none of those and cannot answer the question. `cuda-memcheck` is gone
as of CUDA 12 and compute-sanitizer replaced it, so anything still recommending it is stale.

### nvcc warnings, and the claim they refute

This is where the backlog line "CUDA guidance, nobody, MCMR can own it, no upstream lint does"
breaks. `nvcc --help` lists six `--Werror` kinds, and two of them are exactly what MCMR ships.

```
$ nvcc -arch=sm_89 --Werror default-stream-launch,missing-launch-bounds -c launch.cu
launch.cu(2): error: no __launch_bounds__ specified for __global__ function
launch.cu(4): error: explicit stream argument not provided in kernel launch
      scale<<<1, 32>>>(data);
```

`default-stream-launch` is `CU-LAUN0002`. nvcc owns it, with the preprocessor and the type system,
and reports it as part of the build the project already runs. The other four kinds are
`cross-execution-space-call`, `reorder`, `deprecated-declarations`, and `ext-lambda-captures-this`,
and `missing-launch-bounds` is a CUDA-specific check MCMR does not have.

MCMR's `CU-LAUN0002` also does not enforce its own documented exception. The docstring says a
program that never creates a stream has nothing to serialize against, and the implementation only
tests whether the launch names a stream. On tokenization it reported 12 launches, of which only 4
are in the module that actually creates streams. The other 8 are in `core/encode`, `post`, and
`pre/segment`, none of which mentions `cudaStream_t` anywhere. `CU-MEMO0001` gets this right for
transfers and `CU-LAUN0002` does not.

### ptxas warnings

Four flags that judge compiled device code rather than source. `--warn-on-spills`,
`--warn-on-local-memory-usage`, `--warn-on-double-precision-use`, and `--warning-as-error`. A
register spill is invisible to any source-level reader and is one of the most consequential things
about a CUDA kernel. Nothing MCMR can do reaches it.

### clang-tidy on CUDA

There is no CUDA check group in clang-tidy. The `altera-*` group is Intel FPGA OpenCL, not CUDA.
What clang-tidy has is a Clang frontend that parses CUDA under `-x cuda`, so all 604 generic checks
apply to `.cu` with `__device__` and `__global__` understood. That is worth more than a CUDA group
would be, and getting it to work is the story in the next section.

### Nsight Compute and Nsight Systems

ncu 2026.2.1.0 ships **27 rules** with identifiers such as `AchievedOccupancy`, `CPIStall`,
`MemoryCacheAccessPattern`, `LocalMemoryUsage`, and `LaunchConfiguration`. It is a real rules engine
producing real advice, and every rule needs a profiled run of the kernel and reports about the
kernel that ran. With `-lineinfo` the advice attributes back to source lines. nsys 2026.1.3 does the
same at the timeline level. Both are profiling rather than lint and neither is a competitor. They
are, however, the tools that would tell a project whether `CU-LAUN0002` mattered.

### cuda-gdb and the rest of the toolkit

`cuda-gdb` 13.3 is a debugger. `cuobjdump` and `nvdisasm` read compiled objects. The one toolkit
component that judges source rather than a running kernel is **ctadvisor**, new in recent CUDA
releases, which reports compile-time cost by header and by template instantiation. It needs a
build, and it answers a question nobody else in this document asks. Worth knowing about.

## Configuration cost, measured

This is MCMR's real advantage and it deserves a number rather than an assertion.

**MCMR on all three corpora needed zero configuration.** The default suffix list already holds
every native extension, the default exclusion set already skips vendored trees, and
`mcmr check <path>` produced findings on first run.

**clang-tidy on tokenization needed all of this.** The project does emit a `compile_commands.json`
through CMake, and it is not usable as written, because the CUDA entries are nvcc command lines.

```
error: unknown argument: '--extended-lambda' [clang-diagnostic-error]
error: unknown argument: '--generate-code=arch=compute_89,code=[compute_89,sm_89]'
error: unknown argument: '-Xcompiler=-fPIC'
error: unknown argument: '-ccbin=/usr/bin/g++'
error: unknown argument: '-forward-unknown-to-host-compiler'
error: unknown argument: '-rdc=true'
```

Making it work took a rewriting script that dropped nine nvcc-only flags, swapped the driver for
`clang++`, added `--cuda-gpu-arch`, `--cuda-path`, and `-x cuda`, and defined
`__CUDACC_VER_MAJOR__`, `__CUDACC_VER_MINOR__`, and `__CUDACC_EXTENDED_LAMBDA__` by hand because
cuCollections has `#error "NVCC version not found"` for anything that is not nvcc. After all of
that, four hard errors remain from CCCL's `cuda/std/string_view`, which annotates deduction guides
in a way clang's CUDA mode rejects. The findings above were produced from a partly broken parse.

**clang-tidy on llm-head sees almost none of it, and cannot.** There is no compilation database and
there can never be a static one. The header of the `.cu` file that carries the kernels says why.

```
// CupyModule strips local "#include" lines, so the sibling .cuh headers
// are not referenced explicitly here — they are concatenated alphabetically
// before this translation unit and share a single TU.
```

The translation unit is assembled in Python at runtime by CuPy, per configuration, with `CFG_*`
defines chosen by the launcher. Running `clang -x cuda -M` over that file to compute its include
closure returns **no first-party header at all**. Pointed at a `.cuh` directly, clang-tidy refuses
outright.

```
error: unable to handle compilation, expected exactly one compiler job in ''
```

Run with no database on the `.cu` itself, clang-tidy falls back to "Running without flags", fails
to find `cuda.h`, and reports 15 warnings from a partial parse of that one file.

So on llm-head, clang-tidy, the Clang Static Analyzer, IWYU, Infer, PVS-Studio, and Coverity all
see zero of the 27 header files that hold the entire kernel, and MCMR reads all 29 files in 1.2
seconds. This is not a corner case. NVRTC, CuPy `RawModule`, Triton, and
`torch.utils.cpp_extension.load_inline` all produce code shaped this way, and it is increasingly
how research CUDA is written.

## Fixes

clang-tidy's `--fix` is mature. On a small file with four defects it applied all four, converted
the loop, changed the parameter to a const reference, added braces, removed the `else` after a
return, and declined one fix that overlapped another.

```
clang-tidy applied 8 of 8 suggested fixes.
note: this fix will not be applied because it overlaps with another fix
```

It models safety through `--fix` against `--fix-errors`, it can apply notes separately, and it pairs
with clang-format so the result is not left ugly.

**MCMR applies nothing.** The catalog holds 23 fixes and a five-operation rewrite algebra, and
`docs/autofix.md` describes a backend that renders operations against the parsed tree, applies a
plan atomically, reparses, and keeps the result only when the finding is gone. That backend does
not exist in this checkout, and there is no `mcmr fix` command among the eleven the CLI ships. Of
the 23 fixes, 5 attach to general rules and 18 to Python rules, and none of the 5 attaches to a
rule that fires on any of the three native corpora. On C, C++, and CUDA, MCMR's fix score is zero
against clang-tidy's several hundred fixable checks.

## Output quality

Two problems, both measured.

**Many findings print a docstring summary instead of a situated sentence.** These are real lines
from the tokenization run.

```
buckets.cuh:153:5: ALL-FUNC0006 Detect a one-line public callable without enough behavior or reuse. (True, allowed False)
runtime.cu:1:1: ALL-MODU0002 Measure top-level classes and functions as a deterministic focus proxy. (28, allowed <= 20)
impl.cuh:1:1: CU-MEMO0001 Count blocking transfers issued where stream work is already in flight. (1, allowed <= 0)
```

A reader is told a rule's purpose and a number, not what to look at. Compare a rule that does state
its finding.

```
api.cuh:13:1: ALL-CLAS0001 `BlockRuntime` declares 10 members of its 11 out of order, and
  `built_with_static_map` belongs where `~BlockRuntime` sits (1, allowed <= 0)
```

That second shape is genuinely good and better than most clang-tidy messages, which name the check
and quote the source without saying what to do. The first shape is worse than anything in this
document. Both ship today.

**Locations at line 100 are corrupted.** `mcmr check` renders through a Rich console with emoji
substitution left on, so `:100:` becomes an emoji.

```
tile_merge.cuh💯1: ALL-PARA0001 `rebuild_probe_frontier` takes `length` and `pair_ranks` ...
```

Three occurrences on tokenization, 15 on cuCollections. No editor or CI parser can resolve those
locations, which matters for a tool that means to be read by an agent.

Against that, clang-tidy quotes the source with carets, names the exact check so a reader can look
it up, and traces macro expansions through `note: expanded from macro`. The Clang Static Analyzer
prints the full path that reaches a defect. cppcheck prints its value-flow reasoning as numbered
notes. MCMR prints one line and a number.

## Performance

Honest, and MCMR wins by two orders of magnitude on work that is not comparable.

| Run | Wall time |
|---|---|
| MCMR over tokenization, 33 files | 0.69 s, of which kernel 40 ms and rules 64 ms |
| MCMR over llm-head, 29 files | 1.21 s, of which kernel 84 ms and rules 120 ms |
| MCMR over cuCollections, 206 files | 2.09 s, of which kernel 352 ms and rules 271 ms |
| clang-tidy over the block module, 14 TUs, ten check groups | 62 s |
| nvcc compiling one CUDA TU with host warnings | 11.3 s |
| cppcheck over the block module | 0.43 s |
| cpplint over the block module | 0.34 s |
| compute-sanitizer racecheck on a one-kernel binary | 0.87 s |

clang-tidy is roughly 4.4 seconds per translation unit here because it compiles the whole thing,
CCCL, thrust, nanobind, and CPython headers included, once per TU per check group. About half a
second of every MCMR run is fixed cost, importing the package and discovering the rules, and past
that it costs about 3 milliseconds a file on cuCollections because it parses one file and walks it.
The gap is what the evidence costs. It is also why clang-tidy in practice runs on changed files in
CI with a warm build and MCMR can run on every keystroke.

## Where the other tool is better than MCMR

This section is long because the truth is.

1. **Everything behind the preprocessor.** A macro-defined function does not exist for MCMR.
   clang-tidy reported `copy_ints` and `copy_floats` as declarations and flagged
   `bugprone-macro-repeated-side-effects` on `UNSAFE_MAX(left++, right)`, which is real undefined
   behavior. MCMR reported neither function and neither defect.
2. **Memory safety and undefined behavior.** Nothing in MCMR's catalog answers a use after free, a
   double free, a null dereference, a buffer overrun, an uninitialized read, or a signed overflow.
   The Clang Static Analyzer, cppcheck's value flow, `-fanalyzer`, Infer, PVS-Studio, and Coverity
   all do, each with a path or a value-flow trace behind it.
3. **Real types.** Measured above at 22 percent unsound findings on the single most productive
   rule, and the cause is structural rather than a bug to patch.
4. **Linkage and reachability.** `misc-use-internal-linkage` found 63 declarations that should be
   internal where the two `ALL-REAC` rules together found 30, because linkage is a fact of the type
   system and MCMR's reach graph is lexical.
5. **Include hygiene.** IWYU and `misc-include-cleaner` answer it. MCMR fills `ImportBindingFact`
   for native code and then has no general rule that reads it, so the family is built and thrown
   away.
6. **Applied fixes.** clang-tidy applies them with conflict detection. MCMR applies none.
7. **Standards conformance.** MISRA and AUTOSAR are somebody else's product and MCMR has no
   position and should not want one.
8. **Runtime truth about CUDA.** compute-sanitizer's four tools, ncu's 27 rules, and ptxas spill
   warnings all answer questions no static reader can. The missing `__syncthreads()` in the
   demonstration is the canonical example.
9. **CUDA-specific compiler checks nvcc already ships.** `default-stream-launch` and
   `missing-launch-bounds`, both free, both exact, one of them duplicated by `CU-LAUN0002` less
   correctly.
10. **Interprocedural value reasoning.** Infer and Coverity carry facts across function boundaries.
    MCMR carries edges, not values.
11. **Ecosystem.** clang-tidy has editor integration everywhere, a `.clang-tidy` file per
    directory, `NOLINT` and `NOLINTNEXTLINE` and `NOLINTBEGIN`, `--header-filter`, baselining
    through CodeChecker, and twenty years of accumulated check documentation. MCMR has a CLI and a
    profile name.
12. **Provenance.** `mcmr coverage` now accounts for all 604 clang-tidy checks and all 342 cppcheck
    identifiers. MCMR answers 3 clang-tidy checks natively, records 78 as inapplicable, and names
    523 as unavailable. It has no native cppcheck claim, records 5 identifiers as inapplicable, and
    names 337 as unavailable. The account is intentionally sparse, but it is complete and each
    claim is checked against the C, C++, and CUDA provider boundaries it needs.

## Where MCMR has something they do not

The backlog claims CUDA guidance is unowned. Tested seriously rather than repeated, that claim is
partly false and partly true.

**False for CU-LAUN0002.** nvcc owns `default-stream-launch` natively, and MCMR's version is
weaker because it ignores its own documented exception.

**Arguably true for CU-LAUN0001 and CU-MEMO0001.** Nothing in clang-tidy, cppcheck, nvcc, or
compute-sanitizer reports a `__shfl_sync` that Cooperative Groups would state more safely, or a
`cudaMemcpy` in a translation unit that also creates streams. Both are design guidance rather than
correctness, which is precisely the tier MCMR is built for, and both are static answers to
questions that otherwise only show up in a profile. `CU-LAUN0001` reported 12 raw barriers in
llm-head, 5 in tokenization, and 4 in cuCollections. This is a genuine gap and MCMR does fill it.

**True and much stronger for the JIT-compiled seam.** llm-head is the case. A repository whose
CUDA is assembled and compiled by Python at runtime has no compilation database, so every
compiler-based tool in this document sees nothing, and MCMR reads all 29 files with no setup. This
is the one place where MCMR is not merely cheaper but is the only option, and it is a growing
pattern rather than a curiosity.

**True for the whole-repository measures.** These are real and no C++ linter has them.

* Module coupling and the main sequence. `ALL-ARCH0003` on cuCollections reads the `#include`
  graph and reports that `benchmarks::benchmark_defaults` sits at 3.12 percent instability and
  imports `include::cuco::hash_functions` at 9.68, so every change to the second reaches the 31
  modules that depend on the first. That is Martin's Stable Dependencies Principle computed over a
  header-only C++ library, and it is a useful sentence.
* Git history. `ALL-HIST0001` through `ALL-HIST0003` read churn, ownership spread, and co-change.
  No static C++ tool reads a repository's history.
* Cross-file clone detection over normalized tokens. `ALL-DUPL0003` found 504 pasted blocks in
  cuCollections, most of them in the benchmark suite where they are real.

One caveat on the architecture rules. `ALL-ARCH0004` measures abstractness by counting pure
virtuals, and a C++ template library expresses abstraction through templates and concepts, so it
reports the zone of pain on essentially any header that several others include. The kernel's own
documentation already admits that a contract expressed as a template parameter has no declaration
to point at. The measure is honest for C++ with inheritance and wrong for C++ with templates.

## Defects found while measuring, reported rather than fixed

Every one of these is in MCMR rather than in another tool.

1. **The native frontend drops the receiver from a member call in `SyntaxFact`.** The Python
   frontend keeps it. Measured directly on the same rule.

   ```
   python   probe.py:render    calls: ['name.lstrip', 'subprocess.run', 'bare.upper']
   cuda     erase_bench.cu     calls: ['get_int64', 'generate', 'begin', 'exec', 'insert', 'start']
   ```

   The C++ source is `state.exec(...)`, `map.insert(...)`, `timer.start(...)`. Because the receiver
   is gone, `ALL-FUNC0011` reads nvbench's `state.exec` as Python's `exec` builtin and reported 35
   reflective scope reads on cuCollections, every one false. `ALL-SECU0005` compounds it. The first
   argument of `state.exec(nvbench::exec_tag::sync | nvbench::exec_tag::timer, ...)` is an
   `operation` node, which the rule reads as a command line built from parts, so a CUDA benchmark is
   reported as a shell injection. Four such findings on cuCollections. Every general rule that
   matches a bare builtin name is unsound on C++ for the same reason, and
   `tests/test_language_coverage.py` cannot catch it because its fixture compares binding names and
   never call names.

2. **The interop extractor returns C++ keywords instead of kernel names.** `src/core/src/interop.rs`
   reads a CUDA artifact as the identifier following `__global__` and the first space. On the
   tokenization corpus the complete list of CUDA artifacts it found is `__launch_bounds__`,
   `inline`, `void`, `kernels`, and `cuco`. Not one is a kernel. The extractor's own unit test,
   `a_pybind_macro_and_a_cuda_kernel_name_themselves`, asserts `vec!["void"]` for
   `__global__ void scale(float* data) {}`, so the defect is pinned by a test rather than caught by
   one, under a name claiming the CUDA kernel names itself. Every `ALL-BIND0001` and `ALL-BIND0002`
   finding on a CUDA repository is therefore
   meaningless, which matters because cross-language seams are the capability MCMR most wants to
   claim here.

3. **`ProjectConfigurationFact` and `AutomationTaskFact` are emitted for files that do not
   exist.** Over a directory holding one `.cpp` and nothing else, the kernel produced a
   `ProjectConfigurationFact` keyed `configuration:pyproject` at `pyproject.toml:1:1` and an
   `AutomationTaskFact` keyed `automation:chefe` at `chefe.toml:1:1`, both empty, both declaring
   `language: python`. Two rules then fail on them, so **every** C, C++, or CUDA repository with no
   Python manifest gets a guaranteed `PY-TYPE0003` and `ALL-LIFE0001` finding pointing at files it
   does not contain. This is exactly the fabricated-field class `tests/test_fact_variation.py` was
   built to close, and it survives because every corpus in the ledger has a manifest.

4. **The exclusion globs are not applied to the repository-wide passes.** With
   `--exclude "**/.build/**"`, discovery correctly read 33 files, and the interop pass still
   reported artifacts from `core/bpe/block/.build/_deps/cuco-src/`. The history pass likewise
   ignores `--suffixes`, so `mcmr check --suffixes .cu` reports `ALL-HIST0001` on `.py` files.

5. **`CU-LAUN0002` does not enforce the exception its own docstring states.** Detailed above. Eight
   of twelve findings on tokenization are in modules that create no stream.

6. **Rich emoji substitution corrupts any location on line 100.** Detailed above.

7. **`ALL-PARA0001` is unsound on C, C++, and CUDA** because `native.rs` reads `type_name` from the
   tree-sitter `type` field alone and drops the declarator. 22 percent measured false positives.

8. **The default suffix list omits `.inl`, `.ipp`, `.tpp`, and `.hxx`**, hiding 18 percent of
   cuCollections.

9. **A documentation error.** `docs/backlog.md` line 17 says CUDA guidance is owned by nobody and
   that no upstream lint does it. nvcc's `--Werror default-stream-launch` and
   `--Werror missing-launch-bounds` are counterexamples.

## Where MCMR should borrow next, ranked

Ranked by the finding-per-effort a native repository would actually get, and aligned with backlog
items 17 through 22 where they hold up.

1. **Fix the parameter type, before adding anything.** Reading the declarator so `int32_t *` and
   `int32_t` are different types removes 22 percent of the false positives on the most productive
   rule in the catalog and unblocks backlog item 4, large value passed by copy, which needs a real
   type to be worth anything. This is not a borrow, it is a repair, and no new rule pays until it
   lands.
2. **Fix the receiver drop in the native `SyntaxFact`.** Same argument. It silently turns every
   builtin-name rule into a false positive generator on C++, and there are more of those than the
   two found here.
3. **Backlog 20, missing launch error check.** No `cudaGetLastError` or `cudaPeekAtLastError` in
   the scope holding a launch. This is the strongest genuinely unowned CUDA rule. nvcc does not
   check it, compute-sanitizer only sees it if the error happens, and forgetting it is how a CUDA
   bug goes silent for a week. Tokenization does it correctly everywhere, which is exactly the
   evidence that the discipline is real and worth checking. It needs the launch and the enclosing
   scope's calls in one fact, which `KernelLaunchFact` almost has already through
   `enclosing_function`.
4. **Backlog 17, host round trip inside a device pipeline.** A device-to-host copy whose result
   feeds host control flow or sizes the next device operation. It exists in the tokenization corpus
   already, at `runtime_merge.cu` line 88, where a `cudaMemcpy` of one `int32_t` back to the host
   sits between a kernel launch and the device-to-device copy that the returned value sizes.
   Nothing else in this document reports it, and it is a design defect with a real cost. It needs
   the `EdgeFact` the backlog already names.
5. **Backlog 19, block size that is not a multiple of the warp.** Cheap, `KernelLaunchFact` already
   carries the block dimension as source text, and it is only answerable where the dimension is a
   literal. Worth having, small.
6. **`ALL-COMM0001` needs to stop counting license headers.** A 100 percent fire rate is not a
   measurement. Either the family excludes a leading notice or the profile does.
7. **Backlog 21 and 22, the rule of five and const correctness.** These are the two items I would
   drop. clang-tidy's `cppcoreguidelines-special-member-functions` and `misc-const-correctness`
   both need to know whether a member function mutates and whether a type has a user-declared
   destructor, and both of those need the type system. A tree-sitter approximation would be wrong
   often enough to be turned off. Concede them.
8. **Backlog 18, two-phase CUB temp storage.** Narrow, and it decays as CUDA 13.1's single-call API
   spreads. Low value.
9. **Keep the native account executable.** The clang-tidy and cppcheck inventory and gap files have
   landed. The three clang-tidy claims have direct oracle comparisons. cppcheck inventory
   re-derivation remains unavailable in the free-threaded Python environment because the conda
   package requires the regular CPython ABI, while its captured parser test remains live.

## Should MCMR invest here at all

Mostly no, and the reasoning matters more than the verdict.

**Concede local correctness, memory safety, undefined behavior, security, modernization, and
include hygiene to clang-tidy, the Clang Static Analyzer, and the compiler.** Every one of those
needs the preprocessor, the type system, or a path, and MCMR has none of the three and is not going
to acquire them from tree-sitter. Writing C++-scoped rules for that tier would produce a worse
clang-tidy that a project also has to install. The right posture is the one the ownership boundary
already states, which is to mirror only the design-level checks, and this measurement says even
that should be narrower than the backlog currently plans.

**Concede runtime CUDA to compute-sanitizer and Nsight, without hesitation.** Races, uninitialized
reads, out-of-bounds device accesses, occupancy, spills, and stall reasons are all runtime facts.
compute-sanitizer found the race in 0.87 seconds and MCMR could not have found it in any amount of
time.

**Keep and sharpen the four places MCMR is not competing with anybody.**

* The JIT-compiled CUDA seam, where no compilation database exists and every compiler-based tool
  sees nothing. This is the strongest argument in the whole document and it is worth building
  toward deliberately rather than benefiting from by accident.
* CUDA design guidance that is neither a compiler check nor a profiler result, which today is
  `CU-LAUN0001` and `CU-MEMO0001` and should become backlog items 17, 19, and 20.
* Whole-repository shape, meaning module coupling over the include graph, cross-file clones, git
  history, and the reach graph. These read C++ well enough to be useful and nothing else in the C++
  world offers them.

**Spend the next unit of effort on correctness of what already runs, not on new rules.** Twenty
rules judge native source today and the most productive of them is 22 percent wrong, two rules fire
only false positives on C++, the cross-language artifact list contains no artifacts, and every
manifest-less repository gets two guaranteed false findings. A catalog that added ten C++ rules on
top of that would be less trustworthy, not more. Fix items 1, 2, 3, and 4 of the defect list, then
land backlog 20 and 17, then stop and let clang-tidy have the rest.

The honest summary is that for C and C++ MCMR is a complement that should stay small, for CUDA it
has a narrow real claim that is smaller than the backlog says, and for JIT-compiled CUDA it is the
only tool in the room.
