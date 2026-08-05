# Changelog

- External fact packages can now register typed providers through `mcmr.providers`. Provider
  ownership is exact, settings are namespaced, and only requested families are collected in
  memory.
- Repair safety is declared once on `@rule`. `FixQuery` no longer repeats it and optional node and
  import relations receive typed empty defaults.
- `PY-EXCE0004` detects the exact one-return exception boundary that can become
  `contextlib.suppress` and offers a safe import-aware replacement.
- README, system architecture, and roadmap now center the version 0.0.1 contract and the DataHub
  hackathon delivery path.

All notable changes to My Code, My Rules are documented here.

The format follows Keep a Changelog, and releases are cut from the version in `pyproject.toml`.

## Unreleased

### Added

- `mcmr writeback` publishes one completed run back to the systems that supplied its evidence.
  Providers opt in through a `ResultPublisher` protocol, so no analysis path can publish and no
  configuration turns it on. The DataHub publisher attaches one institutional memory link to each
  governed asset a finding named, which is additive where `updateDescription` would overwrite a
  sentence a person wrote.

- Table-level lineage, recent-change marking, and stated cast types close three silent zeros.
  `LineageEdgeFact` now has a provider through `searchAcrossLineage`, keeping only direct
  neighbours so an impact measure is not computed over a graph where everything is adjacent. A
  `since` setting marks assets DataHub modified after a given day, which is what makes the
  `"changed"` scope of `ALL-DATA0007` and `ALL-DATA0013` honest. An explicit SQL cast becomes the
  stated type expectation `ALL-DATA0003` reads, with both spellings normalized through one
  engine-neutral parser so `NUMBER` and `DECIMAL` agree while `STRING` and `NUMBER` do not.

- `mcmr demo` runs the complete DataHub workflow with no service, no network, and no edit to the
  example it copies. It reports what the catalog says about a pipeline change, previews the one
  repair the catalog proves, applies and verifies it, reruns the rule clean, and prints its own
  timings. A `recorded` provider setting names a directory of captured GraphQL exchanges, each
  pairing request variables with the exact response envelope, so a live capture is a drop-in
  replacement rather than a format change.

- The first repair proven by evidence from outside the repository. `ALL-DATA0002` now carries a
  safe fix that rewrites the literal naming a retired column so it names the column DataHub's own
  column-level lineage says derives from it. The provider retains a successor only where exactly
  one surviving column claims the retired one, and the rewrite is offered only where the literal
  spells the old name once. `DataFieldReference` retains the literal anchor and that rewrite under
  `repair`, and drops the source location its span already carried.

- Three DataHub-backed rules that join catalog context to exact source evidence. `ALL-DATA0011`
  counts unowned assets whose bounded downstream lineage reach meets a threshold, `ALL-DATA0012`
  counts fields the catalog tags sensitive while leaving their owner or glossary context empty,
  and `ALL-DATA0013` reports the source line that reads an asset the catalog gives no owner or no
  description. `DataField` now retains `tags` and `glossary_terms`, which is the governance
  vocabulary the sensitive-field rule reads.

- Two contextual classification backends beside `codex` and `gliner2`. `claude` runs one isolated
  single-turn `claude --print` process per bounded batch, and `openrouter` posts the same closed
  schema to an OpenAI-compatible server, reading its key from `OPENROUTER_API_KEY` at request time
  and never from configuration. Prompt, schema, citation, and batching machinery is now shared, so
  a new provider supplies transport alone. `mcmr model-sweep . --backend <name>` selects one for a
  single stateless sweep.

- Exact evidence-backed autofixes for empty directories, class-owned helpers, grouped unused import
  bindings, unused explicit exports, and explicit `__all__` declarations outside package
  initializers. File and directory changes share one guarded rollback transaction, and every
  applied repair is verified by rerunning its originating rule.
- Cross-file Python moves retain relative and type-only imports. `PY-MODU0003` places an
  initializer function beside its one exact sibling class owner, while `PY-IMPO0005` reuses the
  existing public-facade proof for safe deep-import repairs.

- Seven Numba CUDA and four CUDA Python rules over typed Python call, function, and syntax tables.
  They cover kernel returns, divergent barriers, unbounded grid indices, dynamic local storage,
  streamless transfers and launches, global synchronization, unsupported core construction,
  legacy default streams, and blocking raw memory APIs. Exact kernel decorator joins keep ordinary
  indexed Python calls out of the launch rule.
- A Maturin-built `mcmr.kernel_tables` extension with a free-threaded PyO3 `AnalysisSession`.
  One repository pass now exposes normalized Polars relations for all 85 selected fact families.
  Production fact transport has no JSON stream, temporary spool, or row fallback.
- Shared typed records filled directly by the Python, Rust, TypeScript, C, C++, and CUDA frontends.
  Repository graph enrichment completes those records before the kernel normalizes them into
  specialized and generic relations.
- A complete columnar execution design based on a census of all 278 rules and 85 declared fact
  families. `docs/columnar.md` defines normalized entity and child tables, the direct Rust Polars
  to Python `PyDataFrame` boundary, the free-threaded PyO3 contract, and the completed table-only
  execution invariants.
- One table contract for the complete catalog. Each of the 215 deterministic declarations runs
  once and returns one lazy `RuleQuery`. Each of the 63 contextual declarations runs once, returns
  one candidate `ModelQuery`, and makes one batched backend call. Aggregate values cross into
  ordinary Python results while detailed evidence and relational fixes materialize only for
  bounded failures.
- Specialized FunctionFact, CallFact, ClassFact, ImportBindingFact, and SyntaxFact relations, plus
  typed generic relations for the remaining families. Exact semantic cases cover settings,
  exclusions, ordering, values, findings, spans, evidence, measurements, and repairs.
- A generic `Table[Fact]` boundary backed by a validated ordinary dictionary of enum-keyed Polars
  frames. Plans register through Patos, one coordinator retains selected tables, and there is no
  setting or family branch that can select an alternate execution engine.
- Historical migration measurements for the FunctionFact and CallFact pilots. Five fused function
  expressions ran about 68 times faster than the former row dispatch, the complete CallFact
  judgment ran about 1.83 times faster, and flat CallFact relations retained about one tenth the
  memory of the equivalent Pydantic graph. These measurements explain the design and do not
  describe a production fallback.
- An exact deterministic analysis cache keyed by the repository fingerprint, selected rule
  contracts, policies, settings, exclusions, retained evidence, and the Python and Rust tool
  implementation. A malformed entry discards itself, writes are atomic, `--no-cache` bypasses it,
  and run statistics distinguish hits, misses, reads, and writes.
- `PY-PYDA0007`, which reports arbitrary-length tuple annotations on declared Pydantic fields while
  leaving fixed record tuples and `ClassVar` declarations alone. The provider resolves imported
  `typing.Tuple` aliases and nested tuple shapes without guessing a replacement representation.
- A complete GE4M replacement ledger. Independent packaged inventories account for all 205 old
  rules and all 18 externally meaningful capabilities in both directions. `mcmr replacement`
  validates every live target and reports zero missing capabilities without importing GE4M.
- The ABI-neutral PyPI `cppcheck` wheel as a development dependency. It runs the live overlap,
  listing, and harness oracles inside CPython 3.14t, reducing five absent-tool skips to one explicit
  release mismatch while the newer 2.21.0 inventory remains unchanged.
- Normal `mcmr check` runs contextual rules when `[tool.mcmr.model]` explicitly enables the
  isolated schema-constrained Codex backend. `mcmr backends` shows the exact model, reasoning
  effort, and timeout without starting it.
- `mcmr model-sweep`, which runs every contextual rule through the configured Codex harness with
  bounded concurrency and stable output order. Each result retains its answer, findings, model,
  token counts, and elapsed work, while an empty report, synchronous contextual rule, missing
  provenance, or negative duration fails at the typed boundary.
- Complete JSON check output through `--format json` and `--output`, plus `--report-only` for audit
  jobs that retain findings without choosing a failing status.
- `mcmr catalog`, which exports all 278 live typed declarations directly and replaces a generated
  registry that could drift from execution.
- `mcmr dependencies refresh`, which reads direct Python requirements from `pyproject.toml` and
  `chefe.toml`, prefers exact `uv.lock` resolutions, collects bounded PyPI and GitHub evidence, and
  writes the typed `.mcmr/DependencyFact.json` used by later offline checks. Unknown release,
  project, repository, and yanked states stay unknown rather than becoming healthy defaults.
- Initial public project scaffolding.
- A Rust analysis kernel under `src/core/` that discovers, reads, and parses a repository once and
  builds `ModuleFact`, `ImportBindingFact`, `FunctionFact`, `ClassFact`, `CommentFact`, and
  `CallFact`. It builds only the families the selected rules read, which is the whole dependency
  injection system: a rule cannot receive evidence it did not ask for.
- `mcmr check`, which runs the selected catalog over one native repository session and reports
  aggregate observations with bounded detailed findings.
- `docs/kernel.md`, holding the kernel task list and the definition of done for each phase.
- Twenty-four more fact families in the kernel, covering symbols, attribute accesses, annotations,
  try blocks, comprehensions, collections, strings, literals, branches, enums, exceptions, method
  groups, parameters, prose, queries, runtime type checks, waivers, directories, dependency edges,
  Pydantic models, and pytest tests, plus the project configuration a repository states in its own
  manifest. 125 of the 155 deterministic rules now run from source alone.
- Four TypeScript rules covering what its own linters do not: `TS-MODU0001` wholesale re-exports
  that turn a module's internals into its public API, `TS-MODU0002` how far an import climbs out of
  its own directory, `TS-TYPE0001` constructs that survive type stripping and so block
  `erasableSyntaxOnly`, and `TS-TYPE0002` the share of lines that step around the type system.
- Cross-language seams. The kernel finds the artifacts one language declares and another reaches:
  binaries from Cargo, `pyproject`, and `package.json` manifests, native modules from `#[pymodule]`
  and `PYBIND11_MODULE`, CUDA kernels, and shared libraries loaded by name. A name only counts as
  reached where it is stated as a literal string, since that is how a name actually crosses a
  boundary. `ALL-BIND0001` reports a seam with one side wired and `ALL-BIND0002` measures how many
  languages depend on one artifact.
- A TypeScript frontend on the oxc parser, filling the same fact families as the Python one, so
  every general rule reads TypeScript with no rule changing. `export` is the visibility keyword, a
  `#name` member is private, and an import records whether it stays inside the project.
- `mcmr graph`, which shows what spreads across a repository, what is public but reached only by
  its own file, and what nothing reaches at all. `SymbolReachFact` carries those counts, and
  `ALL-REAC0001` through `ALL-REAC0003` read them.
- The repository graph. The kernel builds a typed structural multigraph with the same node kinds,
  edge kinds, and identities as the Archy oracle, resolving lexical names, imports, `self` and `cls`
  receivers, constructors, and builtins, and leaving what it cannot prove visible as an unresolved
  symbol. On MCMR's own source it matches Archy exactly on definition, import, containment, and
  inheritance edges and on twelve of the fourteen node kinds.
- A policy layer. `Numeric`, `Boolean`, and `Category` policies turn an observation into `pass`,
  `fail`, or `unassessed`, and the `relaxed`, `standard`, and `strict` profiles let a project say
  how much of an opinionated rule it wants. A measurement with no stated interval stays unassessed
  rather than being summed into a number nobody chose. `mcmr check --profile` selects the level and
  exits nonzero only on a failure.
- An evidence store. A fact no parser can derive, such as a runbook or an alert, is read from
  `.mcmr/<FactName>.json`, so the remaining rules run wherever a project keeps those records.
- Eleven rules: cognitive complexity, nesting depth, required parameter count, swappable parameter
  pairs, configuration object parameters, value dispatch candidates, unchecked result calls,
  unbounded blocking calls, commented-out code, and two CUDA rules for blocking transfers inside a
  stream scope and raw barriers where Cooperative Groups states the same synchronization.
- `docs/backlog.md`, which records what to build next and which tool already owns what.
- Fixes are rewrite programs over resolved nodes. `Remove`, `Replace`, `Move`, `Unwrap`, `Rename`,
  and `Inline` each expose the spans they touch, so the engine detects conflicting fixes without
  knowing any rule, and a fix is testable without a provider. `docs/autofix.md` states the contract
  the language backend fulfills, including import management, atomic application, reparse, and
  re-running the rule before an edit is kept.
- A complete Python autofix path. The renderer supports all six rewrite operations with UTF-8 byte
  coordinates, exact retained-source checks, import management, conflict detection, syntax
  validation, unified diffs, atomic writes, rollback, and fresh originating-rule verification.
  `mcmr check --repair preview` previews patches and `--repair apply` writes safe plans to a
  bounded fixpoint. One repair mode makes preview and application mutually exclusive.
- Rich terminal presentation for checks and repository reports. Interactive runs show loading
  states, compact analysis and timing tables, detailed finding panels, source context, evidence,
  measurements, model provenance, repair safety, and readable fix previews. Plain full and concise
  check formats remain available.
- Shared `Visibility`, `MemberKind`, and `ReceiverKind` vocabulary, mapped to each language in
  `docs/generalization.md`, with the remaining generalization candidates ranked.
- Recorded runs, so MCMR can say whether a repository is getting better rather than only what it is
  today. `mcmr snapshot` writes one readable JSON file per run under `.mcmr/runs`, holding the
  commit and whether the tree was clean, the profile, and for every selected rule the bar it was
  held to, how many observations it made, and every site it failed at beside the value it read
  there.
- `mcmr diff`, which holds a repository against a recorded run and reports what appeared, what was
  resolved, what grew where it stood, and what eased. Two runs judged under different profiles are
  refused rather than subtracted, and a rule the baseline never held, one the catalog has dropped,
  and one whose contract or bar moved each travel in a list of their own, so a rule added after a
  baseline was taken can never read as a regression. It exits nonzero on a regression, which makes
  it a gate.
- `mcmr trend`, which draws the runs a repository recorded under one profile in the order they
  happened, with each direction counted over only the rules two consecutive runs judged the same
  way and the catalog fingerprint printed beside it.
- `mcmr simulate`, which answers what adding or removing imports would do to the shape of a
  repository without editing a file. It reports the cycles and topological back edges the change
  would form or break and how the MacCormack propagation cost moves, over the same import
  projection the design structure matrix and the blast radius already read. It agrees with the
  Archy oracle exactly on all three.
- `CommentFact` from the Rust frontend and from the C, C++, and CUDA one, which the Python
  frontend alone used to fill. The whole `ALL-COMM` family read an empty stream for four languages
  the catalog claimed to cover, so every rule in it answered zero there and nobody could tell that
  apart from a clean repository. One shared reader groups, sizes, and addresses the comments, and
  each language answers only the two questions it alone can settle, which are whether a comment
  addresses a tool and whether it is code rather than prose. Rust needs a lexical scan for this,
  since `syn` drops every comment that is not documentation.
- `SyntaxFact` from the C, C++, and CUDA frontend, mapped onto the same 23-kind neutral vocabulary
  the Python and Rust frontends already fill, so `ALL-NAMI0001` and `ALL-CONT0002` run on those
  three languages unchanged.
- `CallFact` from the Rust frontend, which had the same hole: two general rules over calls could
  never fire on Rust.
- `tests/test_language_coverage.py`, which holds the kernel to the claim. It takes what the
  reference frontend answers over one fixture as what a general rule was written against, runs the
  same program in six languages, and requires every other language to answer the same families. A
  language that answers less has to be written into the gap table with its reason.
- `mcmr coverage`, which accounts for every rule an upstream tool ships and says what MCMR does
  about each one. It reads a frozen inventory per tool and derives the account from the rules
  themselves. Pylint reads 22 native, 269 delegated, 6 adapted, 19 inapplicable, and 73 unavailable
  over 389 messages, Ruff reads 34 of 968 generalized, and Clippy 10 of 809. Its default view
  summarizes all seven inventories and 3,538 rules in one table, while `--tool` opens the full
  per-rule account for one tool.
- A machine-readable grammar for the `References` section of a rule docstring. A line reading
  `relation tool identity [identity]`, where the relation is `Generalizes`, `Adapts`, or `Cites`,
  names one rule of one upstream tool. Everything else stays prose, and a bare URL line attaches to
  the entry above it. Every named reference is checked against that tool's frozen inventory, so a
  reference to a rule the tool does not have fails the suite.
- `mcmr.inventories`, which regenerates each frozen inventory from the tool itself: Pylint through
  its own message store, Ruff through `ruff rule --all`, and Clippy through `clippy-driver -W help`.
  The suite re-derives all three and fails when a frozen copy and an installed tool disagree.
- Frozen ESLint, typescript-eslint, clang-tidy, and cppcheck inventories, bringing the reference
  table to seven inventoried tools. Each tool profile states its language boundary, and a general
  coverage claim counts only where the provider ledger proves that its fact family exists.
- `SyntaxFact` from the TypeScript frontend. The shared unused-expression and debugging-artifact
  rules now agree with ESLint on executable fixtures rather than merely naming its rules.
- Direct oracle comparisons for clang-tidy `bugprone-unused-return-value` and Clippy `no_effect`,
  completing executable checks for the native claims added to the reference table.
- `mcmr/data/<tool>.gaps.json`, holding the written reason for every rule of a tool that MCMR does
  not answer, beside that tool's inventory rather than in code, because a gap is a statement about
  the upstream tool and no MCMR rule exists to carry it.
- A TypeScript graph frontend, so the language reaches the repository graph rather than stopping at
  the fact families. Modules, classes, interfaces, type aliases, enums, functions, methods,
  properties, attributes, variables, and parameters all become nodes, and containment, definition,
  import, call, instantiation, inheritance from both `extends` and `implements`, type, and access
  all become edges. Specifiers settle the way TypeScript settles them, through extensionless
  relative paths, `index` files, `.d.ts` declarations, and the aliases a `tsconfig.json` states
  across its `extends` chain, and a re-export is followed to the module that declares the symbol.
  Everything downstream now reads TypeScript: `ModuleCouplingFact` and so `ALL-ARCH0003` through
  `ALL-ARCH0005`, `OverrideFact`, `SymbolReachFact`, the class and package diagrams, the design
  structure matrix, and the impact set. On a 113-file SvelteKit project this is 2,144 nodes and
  4,945 edges where there were 180 and 179.
- `tests/test_fact_variation.py`, which finds a fact field a provider never varies. It builds every
  family over this repository and over a small written project stating the shapes this one lacks,
  and holds every field that never moves to a ledger with the reason, failing in both directions so
  a newly frozen field and a stale entry each turn the suite red. It records 160 fields and three
  families today, tells apart a field no frontend writes, a literal every frontend states, and a
  field the corpus simply never moves, and it found one more unsatisfiable rule in `PY-COLL0002`.
- A registry of works in `src/api/mcmr/data/works.json` and an influence table derived from it. Every
  work a rule may cite is registered with its canonical title, its kind, its author, and its link,
  which is what a generated rule page needs to render a citation. `InfluenceReport` reads the whole
  catalog and reports, per source, how many references were made and how many rules made them, with
  the tool half and the literature half in one table and told apart by kind. `A Philosophy of
  Software Design` is the largest literature influence at 32 references across 32 rules.
- A formal docstring template and reference grammar in `SYSTEM.md`, each stated as the expression
  the code runs rather than as a description of one. `tests/test_rule_template.py` holds every rule
  to the template, holds every References line to `ReferenceParser.grammar`, and checks that what
  `SYSTEM.md` prints is character for character what the parser uses.

### Fixed

- A contextual classification prompt now states what selecting each category reports. A category
  name says what the model observed and never what the engine will do with it, so a rule offering
  `appropriate` beside `use_plain_class` read as two recommendations while the policy scored the
  second one as a defect, and a class the model judged perfectly fine arrived as a failure whose
  own message argued that it was fine. The resolved policy answers `Policy.reported`, the query
  carries the outcome map into the shared instructions, and the model is asked for the category
  the evidence states rather than the one whose report it would prefer. `PY-MODE1001` and
  `ALL-STAT1001` also separate the categories their definitions used to overlap, so `use_plain_class`
  names a class that has to come off a model and `shared` names state with no governing contract
  to point at.

- `PY-DOCU0002` reads a tensor name only where a tensor library owns it. `Array`, `Tensor`, and
  `ndarray` are ordinary words that many libraries spell the same way, so `tomlkit.items.Array`
  was reported for missing shape and dtype prose about a TOML array. The name is now resolved
  through the file's own imports to the library it came from, and only `torch`, `numpy`, `jax`,
  `cupy`, `jaxtyping`, and `torchtyping` make it a tensor, which is the exception the rule always
  stated for unrecognized libraries.

- The history family names only files the working tree still holds. Renames were already followed
  forward, but a file deleted or taken apart since, whether in a commit or in the working tree,
  kept its churn and its co-change pairs, so `ALL-HIST0003` could ask a reader to find what two
  files assume while naming one that no longer exists. Every claim this family makes is one a
  reader acts on by opening the file, so a path with no file behind it now votes on nothing.

- `ALL-BIND0001` judges only the artifacts a language declares to reach another one. A packaging
  entry point is now its own `console-script` mechanism rather than a binary, since the target of
  `project.scripts` or a Node `bin` entry is a callable the declaring language already holds, so a
  pure Python or pure TypeScript command was reported forever for having no caller in a second
  language. The seam width rule still counts every language that crosses one.

- `PY-MODE0003` establishes project model policy from what a repository owns rather than from a
  folder name. A module whose dotted name merely ended in `bases` used to establish the policy, and
  the foundation itself was recognized only in a file named `bases.py`, so a project keeping its
  bases in `core/bases/strict.py` had its own foundation reported for deriving Pydantic directly
  and renaming the folder was the only way to quiet it. Policy is now established by importing a
  house home or by owning a base that declares no fields and that other classes derive, and a base
  whose body states `model_config` is read as the foundation wherever it lives.

- `PY-MODE0006` leaves a model foundation alone. A base that owns no fields and either states the
  `model_config` its subclasses inherit or is already derived by classes that own fields states
  policy rather than declaring empty data, so config-only bases and an extras-only flexible model
  are no longer reported while a genuinely empty leaf model still is.

- `ALL-CONF0001` reads every entry of a collection before calling it a path. A regular expression
  is not a filesystem path however the name around it is spelled, so a coverage exclusion table
  such as `("pragma: no cover", "if TYPE_CHECKING:", "\.\.\.")` and a rename or lint pattern list
  now abstain where the backslash escapes in them used to read as Windows separators. The test is
  the value rather than a table of known tool keys, because every tool spells its key differently
  while every regular expression is written the same way, and a Windows path such as
  `build\temp` still reads as the path it is.
- `ALL-HIST0003` states one finding per unexplained pair, located at the first of the two files
  and naming both. The count used to arrive as one aggregate row against the history fact at no
  path at all, so a repository was told how many hidden pairs it had and never which ones.

- Prose segmentation keeps a backtick code span whole, so the dot inside `index.md` ends a file
  name instead of a sentence. `ALL-WRIT0005` no longer reads a suffix such as `md` or `toml` as
  the word a sentence opens with. A run of backticks opens the span and the next run closes it,
  which covers the doubled and fenced spellings too.
- A parameter written through a subscript now reads as a mutation. `values[key] = held`,
  `del values[key]`, and the augmented form reach `__setitem__` and `__delitem__` rather than the
  lookup the same expression means on the right of an assignment, so `PY-COLL0001` stops asking a
  mutated mapping parameter to narrow to `Mapping`.
- `ALL-SECU0005` matches a launcher written with a receiver against the whole callee, so
  `platform.system` reads a machine name and is no longer reported as a shell launch while
  `os.system` still is. A launcher written on its own still matches on its bare name, which is how
  C and PHP spell `system`, and `also_through_a_shell` still matches the last segment.
- `PY-FUNC0001` exempts the members of a class inheriting `Protocol`. A structural declaration such
  as `def read1(self, size=-1, /)` copies the positional-only marker of the object it describes, so
  the marker is the contract rather than a hidden public name.
- The `ALL-CLAS0001` member move keeps a blank line inside a moved docstring empty. Reindenting no
  longer writes the destination indentation onto a line holding no text, so a repaired file gains
  no trailing whitespace.
- Python stub files now receive their real import module name without the `.pyi` suffix. Imports
  of native declarations therefore reach the public symbols stated by their PEP 561 stub instead
  of leaving those declarations falsely unreferenced.
- The Archy matrix oracle now states its stub limitation explicitly. It compares runtime modules
  after removing Archy's package fallback for imports whose actual target is a stub.
- `ClassFact` now distinguishes structural typing protocols from runtime implementation classes.
  The nonpublic top-level class rule accepts an intentionally private `Protocol` while still
  reporting private concrete classes, so internal invocation contracts do not have to become a
  false public API.
- Every rule now returns its value beside precise findings. Deterministic findings name the exact
  declaration or record that qualified, while model findings retain each criterion, confidence,
  evidence identifier, provenance, and local decision-table result. The completed catalog guard
  rejects any scalar-only rule.
- Reach findings now use declaration spans, typing placement findings name exact declaration and
  import spans, inherited class-method calls reach their receiver class, and pytest strictness and
  import mode reflect the effective command-line and configuration controls.
- Four invalid provider states found by the property sweep are no longer constructible. Duplicate
  and type-escape counts cannot exceed their totals, comprehension loop counts are nonnegative,
  and comment normalization requires a positive denominator. The rules keep no clamps, so a
  provider violating one of these contracts fails at the model boundary.
- Python implementation size no longer counts a leading docstring, blank lines, or comment-only
  lines. On MCMR itself this removes 130 false long-function failures while leaving executable
  statements unchanged.
- A nested Rust test module that imports its parent no longer becomes a one-file architecture
  cycle. The graph retains the lexical import, while the module projection recognizes that both
  ends live in the same file. Explicit source-level self imports remain cycles.
- Clone detection now fingerprints implementation blocks rather than whole files. Imports,
  declaration headers, structured rule documentation, and constant tables no longer become pasted
  code merely because a framework gives many files the same shape. MCMR's own clone findings fall
  from 988 to 157 while the Symilar comparison and renamed-local cases remain exact.
- Clone findings now say that normalized token structure repeats, which remains true when comments
  and formatting make the two physical line counts differ. Stable dependency findings state the
  percentage unit on both modules rather than only the importer.
- The native frontend left every function's `control_increments` empty. It now records conditional,
  loop, switch, exception, and else-chain increments with their nesting depth, so conditional count
  and cognitive complexity agree with clang-tidy and with the same program written in Python.
- Native call resolution tried a bare file-stem module before a same-named declaration in that
  module. It now resolves scoped candidates first, so same-file calls credit the function they
  reach and the cppcheck comparison no longer has to excuse a missing edge.
- `TS-MODU0002` claimed to generalize typescript-eslint `no-restricted-imports`, though it measures
  relative import distance rather than enforcing a configured restriction list. The relationship
  is now correctly recorded as adapted.

- The native frontend read a parameter's type from the word beside it and dropped the declarator,
  so `int32_t *__restrict__ tokens` and `int32_t seg_start` both arrived as `int32_t` and read as
  interchangeable. A parameter now carries the type a caller sees, which is the base type, the
  qualifiers that reach the value handed over, and the shape the declarator wraps around it, while
  a qualifier written at the level that binds the name is dropped because no caller can observe
  one. `ALL-PARA0001` falls by 22 percent on a CUDA tokenizer, 29 percent on a CAGRA port, and 16
  percent on cuCollections, and against clang-tidy's `bugprone-easily-swappable-parameters` on the
  same subtree it now names every declaration the oracle names and three fewer that it does not. A
  position a caller may leave out is also kept rather than dropped, so a pair that is not adjacent
  is no longer compared as though it were.
- The native frontend dropped the receiver from a member call, so `state.exec(...)` arrived as
  `exec` and every general rule matching a builtin by name was unsound on C, C++, and CUDA.
  `ALL-FUNC0011` reported 35 reflective scope reads on cuCollections, all false, and they are gone.
  The Rust frontend had the same defect and it is closed the same way.
- `src/core/src/interop.rs` read a CUDA artifact as the word following `__global__`, so the complete
  list it found on a real tokenizer was `__launch_bounds__`, `inline`, `void`, `kernels`, and
  `cuco`. A kernel is now named by the identifier its parameter list opens on, past the return
  type, a launch bound, and a template argument list, and a marker inside a comment declares
  nothing. The same corpus now yields 19 real kernel names. Its unit test asserted `vec!["void"]`
  under a name claiming the kernel named itself, so the defect was pinned by a test rather than
  caught by one, and that test now asserts the kernel's name.
- A repository holding no manifest was given a `ProjectConfigurationFact` at `pyproject.toml:1:1`
  and an `AutomationTaskFact` at `chefe.toml:1:1`, both empty, both declaring themselves Python, so
  `PY-TYPE0003` and `ALL-LIFE0001` failed against files it does not contain. A file the repository
  does not hold now states nothing.
- `--exclude` reached the walk and not the cross-language scan, and `--suffixes` reached the walk
  and not the history, so a run narrowed to CUDA still reported artifacts out of an excluded
  dependency tree and ranked Python modules by churn. One compiled scope now answers for every pass
  that reads the tree.
- Discovery skipped build output and never skipped generated output, so most of what a report said
  about a real front end was about code a generator wrote. `.svelte-kit`, `.next`, `.nuxt`,
  `.output`, `.astro`, `.wrangler`, and the tool caches join the defaults, which are now always
  applied with whatever a caller adds on top rather than replaced by it. On two SvelteKit projects
  the generated half was producing 230 findings against 138 real ones and 303 against 93.
- The default suffix list omitted `.inl`, `.ipp`, `.tpp`, and `.hxx`, which is where a C++ template
  library keeps its bodies. On cuCollections that hid 26 files, 13,757 lines, and 583 functions.
- `CU-LAUN0002` ignored the exception its own documentation states. A launch takes the default
  stream harmlessly where no other stream exists, so `KernelLaunchFact` now says whether its
  translation unit meets a stream at all, and the rule falls from 12 findings to 2 on a tokenizer
  and from 51 to 2 on cuCollections, keeping exactly the launches in units that create streams.
- `ALL-COMM0001` failed all 206 files of cuCollections on the Apache notice each of them opens
  with. A licence is the same words in every file of a project and says nothing about the file, so
  it is left out of the measurement and the rule reports 51.
- `ALL-SECU0005` read any operator on a launcher's first argument as a command line assembled from
  parts, so `state.exec(exec_tag::sync | exec_tag::timer, ...)` was reported as shell injection. A
  command line now has to state part of the command inside it.
- `mcmr check` rendered through a Rich console with emoji substitution on, so every location on
  line 100 came out as `tile_merge.cuh` followed by a glyph and no editor or CI parser could open
  it.
- The `[*]` marker was printed for any rendered edit, promising that a repair marked for review was
  safe to apply unattended. The mark now reads the repair's safety, and a repair wanting a reader
  first prints `[?]` rather than nothing, since hiding it would trade an overstatement for an
  omission.
- `FunctionFact` and `ClassFact` fabricated 59 fields between them, which is 18 rules that read a
  literal as evidence and answered the same thing over every repository. Every claim a file can
  settle is now read off that file. A decorator says whether a member is a property, abstract, an
  overload, an override, a validator, or held in a cache, and whether something other than this
  project decides when it runs. A body says whether it reads its receiver, calls itself, hands its
  one parameter to one call unchanged, checks the type of what a caller passed, raises what a
  declared field would have raised, or builds the class holding it. A signature says which
  parameters carry a tensor and whether the docstring settled its shape and its element type, and
  which defaults are flags. A class says its keywords, the registry key it restates, the fields it
  copies off a component it already keeps, the siblings a static method reaches through the owner
  name, and the ordered regions its members sit in. Only the asyncio a file actually imported
  counts as scheduling work, so a project function named `create_task` is no longer read as one.
- Who subclasses a class, who builds one, who imports it, and what its bases already supply are
  questions about every module at once, so `src/core/src/classes.rs` reads the repository once and
  joins them, the way the exception pass already does. That fills the resolved inheritance graph,
  the instantiation and export evidence, the order-sensitive base collisions, the proposed home for
  a reused model, and whether one callable takes part in dispatch anywhere.
- Seven fields no rule read at all are gone, together with the two they duplicated.
  `FunctionFact.is_special` was `is_protocol_name` under a second name, `documentation_kind` could
  only ever say `callable` on a callable family, and `owner_class`, `default_cluster_size`,
  `is_first_data_parameter`, `control_increments[].is_nesting`, and `ClassFact.ancestor_depth` had
  no reader. `returns_stateless_project_class` asked a cross-file question `PY-CACH0001` does not
  need, so the rule now reports a `cached_property` that never reads its receiver, which is the
  defect it was named for.
- `direct_statement_count` no longer counts the docstring, which all three rules reading it already
  said in their own definitions, and `ALL-CLAS0001` no longer refuses to sort a class holding a
  member kind the configured order leaves out.

- Four providers stated a hardcoded constant where a rule read evidence, which is a rule that
  answers the same thing forever and reads exactly like a clean repository. `CollectionFact` now
  counts every read of a local literal it binds, so `PY-COLL0003` can prove a representation is
  interchangeable instead of never firing. `ExceptionFact` became a repository-wide pass that
  resolves the modules importing each project exception, including through relative imports, so
  `PY-EXCE0003` can see a shared contract. `AutomationTaskFact` derives whether a command stays
  inside the checkout and whether it runs unattended, and reads every task table chefe supports, so
  `ALL-LIFE0001` can fail rather than only pass. `BranchFact` arms carry the size of the body they
  select and whether it hands a value back. Over `~/projects` the first two rules now report 34 and
  12 findings where they reported none, and a `sudo chsh` three lines into a dotfiles task is
  reported as a command the machine rather than the repository carries.
- A TypeScript class member reported its visibility from the name rather than from the class, so a
  `#name` method read as public and the `private` and `protected` keywords were not read at all.
  `FunctionFact` now states what the class declared.
- `AttributeAccessFact.is_inside_owning_class` could never be true, because the walk set the owning
  flag on the `def` statement and then read the accesses of its body, where the flag was gone. Every
  `self.x` inside every method therefore read as being outside its owning class, and `ALL-ENCA0001`
  reported protected access from inside the very class that owns the attribute. The walk now carries
  the innermost lexical class down into the bodies it encloses, so `self`, `cls`, `super()`, and the
  class's own name are owner access wherever they are written, and it reads assignment targets too,
  so a protected write from outside is reported the way Pylint reports it. Over `research` the rule
  falls from 12,590 findings to 2,304, over `aizk` from 159 to 30, and over `ge4m` from 51 to 0.
- Twelve more providers stated a constant where a rule read evidence. `CollectionFact` derives the
  pair tables a callable binds and the lookup loops that read them, `AttributeAccessFact` resolves
  the enumeration a receiver holds, `RuntimeTypeCheckFact` reads the block a check guards,
  `ParameterFact` classifies every use of a parameter and says whether it recognized all of them,
  `LiteralGroupFact` keys a repeated string by the role it occupies and reads the mappings an enum
  keys, `ProseSegmentFact` splits a docstring into paragraphs, `PydanticModelFact` measures the
  plain classes a model would state better, `TypeAnnotationFact` tells a reusable constraint from
  metadata about one field, `WaiverFact` reads the `reason`, `since`, and `expires` fields a
  suppression states, `TestFunctionFact` reads collection, fixtures, calls, module-state writes and
  parametrization, `TestCaseGroupFact` groups siblings by the syntax left once the literals are
  removed, and `SymbolFact` names the scope that binds each name. Eleven rules that could not fire
  now do: over `research` `PY-INTE0001` reports 196, `ALL-PARA0002` 1,189, `PY-COLL0001` 537,
  `PY-TEST0008` 204, `PY-TEST0013` 127, `PY-TEST0003` 71, `PY-TEST0014` 15 and `PY-ENUM0002` 9,
  and over `aizk` `PY-TEST0009` reports 100 calls to `asyncio.run` inside a synchronous test.
- The differential oracle compared file paths where it claimed to compare findings. The
  `protected-access` case asserted that both readers named `generated.py`, which is true of any
  answer on a one-file tree, and the work-marker case compared fact spans that all start at line
  one. Both now compare the findings themselves, and every count-against-count assertion in the
  Ruff and Pylint oracles compares the lines or the declarations instead.

### Changed

- `ALL-FILE0003` exempts a definition catalog by default. The rule documented a catalog as
  measuring zero under the default while the signature declared `allow_definition_catalogs=False`,
  so the two disagreed. A catalog is recognized from what its modules declare rather than by path,
  which is what makes the exemption safe to hold open, and a project that does not organize
  anything that way sets the setting false for the raw count everywhere.

- The class family states `states_model_configuration` for every class, which is what lets a
  foundation be recognized from its body instead of from the file name around it.

- `ALL-HIST0001` is a measurement rather than a defect and owns an unbounded `Numeric()` policy
  beside `ALL-DUPL0003` and `RS-OWNE0001`. Every threshold it uses is relative, so the busiest
  file always reaches its own share and a ceiling of zero would fail every repository with a long
  current file however carefully it was written, which is the module size rules restated. A
  project that wants a churn budget states a numeric policy for the rule under `tool.mcmr` and the
  count is judged against that ceiling as before.

- A rule whose language the analyzed repository does not hold now leaves the selected scope
  instead of reading as skipped. A selection a language could narrow reads the per-module family
  once, so every run knows which languages the repository is written in, and the report counts
  only the rules that repository can answer for. The self-scan of this repository reads
  `215/215 rules, 0 skipped` where it read `215/222 rules, 7 skipped`, and a rule skipped for any
  other reason, such as a missing external provider or a configured disabled rule, still reads as
  skipped.
- Packaging now uses Maturin so the Rust table extension and Python package ship as one wheel.
  Polars comes from Conda in development because its free-threaded runtime wheel otherwise falls
  back to an unsupported source build. The unavailable Python 3.15 preview environment was
  removed so it no longer prevents the default environment from resolving.
- Rule execution now uses one in-process `AnalysisSession` and one registered table path for every
  selected family. Family-specific flags, coordinator branches, row adapters, and execution
  switches are gone.
- Call providers now build typed records directly in Python, Rust, C, C++, and CUDA frontends.
  Repository graph resolution enriches those records before direct relational normalization.
- `PY-TYPE0001` now describes `from __future__ import annotations` precisely for Python 3.14 and
  newer. The import is unnecessary for deferred evaluation but remains supported because it
  explicitly selects the older PEP 563 stringized representation, so its removal stays a review
  fix rather than being presented as removal of deprecated syntax.
- Historical migration evidence showed why the dual transport was retired. Bounded CallFact
  spooling reduced an isolated whole-monorepo row pass from 177.6 to 140.2 seconds, while a complete
  10,900-file row check still took 499.3 seconds and peaked near 4.0 GiB in the kernel and 1.1 GiB
  in Python. Earlier unbounded row runs approached 10.5 GiB and 5.5 GiB. Production no longer uses
  that transport.
- Historical free-threaded validation experiments measured 2.20 through 2.34 seconds sequentially
  and 1.64 through 1.76 seconds by family under the regular interpreter. Three bounded GIL-free
  runs moved from 584 through 792 milliseconds sequentially to 462 through 473 milliseconds by
  family. Per-item threading and a fresh asynchronous event loop were slower. Production now lets
  Rayon own native construction, Polars own row parallelism, and the contextual backend own bounded
  request concurrency.
- Provenance is stated on the rule and the coverage of any tool is derived from it, rather than
  maintained by hand in a table beside it. Each of the 278 rules names the upstream rules it
  generalizes, adapts, or merely cites in its own `References` section, and two copies of one fact
  can no longer drift apart. The Pylint arithmetic is unchanged by the move.
- The literature half of that provenance is exact too. It was free prose, so `Fluent Python` and
  `Luciano Ramalho, Fluent Python` were two rows for one book and 754 prose lines looked like some
  445 works of which 362 appeared cited once. A work is now written `Cites "Title", locator`, the
  quotes make it syntactically distinct from a tool without inferring anything from the shape of
  the words, and the author never appears because the work is the identity. The 825 references the
  catalog states resolve to 201 exact sources, 192 registered works and 9 tools, of which 99 are
  cited once. A title nothing registers fails the parse and a registered work nothing cites fails
  the guard.
- A rule docstring closes its quotes on their own line. A References section ends in a quoted work
  title, and a line ending in a quote written against the closing quotes is not valid Python.

- A repair is now one lazy `FixQuery` beside the rule's value and finding queries. The collector
  materializes normalized rewrite, node, and import rows only for bounded failures and decides
  whether they form a `FixPlan`. The `Insert` operation is gone because no repair used it.
- A type reference is an edge. An annotation is a dependency in every typed language and left no
  other trace, so a class used only in signatures read as unreached by everything. Unreached public
  declarations in this repository fell from 177 to 76.
- Autofix works end to end. The kernel now addresses a callable's single body expression and every
  call site that names it, so `single_use_trivial_helper` produces a real rewrite program: replace
  the call with the body, then remove the declaration.
- Six rules compared visibility against the Python spelling that predates the shared vocabulary, so
  none of them fired on a module-scope `_name`. They now ask whether a declaration is public.
- A percentage policy states its direction. Coverage is judged by a floor and a density by a
  ceiling, and only the rule knows which it reports, so each density rule carries its override.
- Repairs the self-scan found in MCMR's own source: `MethodAnalysis.order_key` and `Rule.invoke`
  take their same-typed arguments by name, since a caller could transpose them silently; the
  kernel's family list became a function rather than a module constant other files import; four
  predicate helpers now read as the questions they answer; and a `setup` task exists because the
  kernel has to be built. Three rule defects surfaced the same way and were fixed: swappable
  parameters ignored keyword-only arguments, the parameter extractor claimed uses it had not
  resolved, and rule modules named after testing were treated as pytest test files.
- The rule engine no longer schedules facts on bounded AnyIO workers. It invokes each declaration
  once, lets Polars evaluate the complete family relation, and collects aggregate values plus
  bounded failure rows. Contextual declarations preserve bounded concurrency behind one batched
  backend request per rule.
- Scope now names the language a rule answers for, with `rust`, `typescript`, `cpp`, and `cuda`
  beside `general` and `python`. A rule whose language no fact carries is skipped and counted
  rather than refused.
- Class method order, top level nonpublic classes, and external nonpublic member access moved from
  the Python scope to the general scope. Method order now takes an orthogonal `visibility_order`
  and `kind_order` instead of one Python-shaped category list.
- Call sites carry resolved argument expressions instead of precomputed verdicts and normalized
  pattern strings. The Torch rule that matched one exact expression now folds any nested chain of
  tensor functions into the fluent chain it is equivalent to, choosing in-place methods when the
  value is rebound to its own tensor.
- Enum value reads are attribute accesses rather than calls, which is what they are.
- Numeric fact fields state their domain as `NonNegativeInt`, `PositiveInt`, `NonNegativeFloat`, or
  the bounded `Ratio` alias instead of repeating `Field` constraints.
- `mcmr check` takes `--exclude` like every other command that reads a repository, and it now
  applies the same vendored and build defaults they do. It also runs through the same `Judgment`
  that `mcmr snapshot` records, so the failures a reader is shown and the failures a baseline holds
  can never disagree about what was found.

### Removed

- Selectable policy profiles and `mcmr check --profile`. Every rule now owns its one acceptance
  contract, and project configuration may only replace that contract with a validated rule-level
  override. The tool has no named acceptance mode.
- The executable GE4M source tree and its two dedicated workflows after the independent replacement
  audit reached all 205 rules and all 18 externally meaningful capabilities. MCMR retains the four
  frozen ledgers as packaged audit evidence and has no GE4M runtime dependency.
- `mcmr/pylint.py` and the `mcmr ledger` command, replaced by `mcmr/upstream.py` and
  `mcmr coverage`. A module named after one tool was the wrong shape for an engine that fronts six
  languages and generalizes patterns from Pylint, Ruff, Clippy, clang-tidy, and SonarSource alike.

- Provider-precomputed fix candidates on facts, and the `fix_plan` lookup that retrieved them by
  name.
