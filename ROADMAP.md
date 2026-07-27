# Roadmap

## Phase one

- [x] Standalone MCMR package and Chefe environment
- [x] Typed rule and fact contracts
- [x] Synchronous and asynchronous rule declarations
- [x] Zero or more typed fixes through `@rule.fix`
- [x] Typed rewrite algebra with conflict spans, replacing provider-precomputed edits
- [x] Shared visibility and member vocabulary, with three rules generalized onto it
- [x] Language scopes for Rust, TypeScript, C++, and CUDA, with per-language rule selection
- [x] Bounded free-threaded execution with chunked fact batches
- [x] Stable path-derived identifiers with conflict failures
- [x] Full reStructuredText rule documentation
- [x] All 205 GE4M declarations migrated without catalog metadata loss
- [x] Unused import and Boolean predicate naming declarations
- [x] Mock typed fact planner and dispatcher
- [x] Cold discovery, warm discovery, planning, execution, and fix planning measurements
- [x] Ruff, Mypy, Pyrefly, Ty, full branch coverage, and package build gates

## Phase two

- [x] Freeze provider and workspace protocols from representative rule implementations
- [x] Rust analysis kernel with discovery, the Ruff parser frontend, and six fact families
- [x] Fact families built only when a selected rule reads them
- [x] `mcmr check` running the real catalog over a repository
- [x] Differential agreement with Ruff on unused imports
- [ ] Add incremental source discovery and language-neutral spans
- [ ] Repository graph, then Pylint, Pyreverse, and Symilar parity, per `docs/kernel.md`
- [ ] Compare facts and rule outputs with GE4M, Astroid, Pylint, Vulture, Lizard, and Archy oracles
- [ ] Render rewrites per language, including trivia and import management
- [ ] Add safe edit conflict detection, previews, atomic application, and reparse verification
- [ ] Profile provider costs through Mainboard
- [ ] Prototype a Rust provider only for measured bottlenecks
- [ ] Differential-test every migrated rule against its GE4M implementation as the oracle

## Later phases

- [ ] Add Rust, TypeScript, C, C++, and CUDA C++ providers
- [ ] Add repository graph, history, dependency, deployment, and operational providers
- [ ] Add GLiNER and harness judgment providers with reproducibility measurements
- [ ] Add external rule packages and project-local plugins
- [ ] Add generated rule reference pages when the contracts are stable
