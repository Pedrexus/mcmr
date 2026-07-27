# Changelog

All notable changes to My Code, My Rules are documented here.

The format follows Keep a Changelog, and releases are cut from the version in `pyproject.toml`.

## Unreleased

### Added

- Initial public project scaffolding.
- A Rust analysis kernel under `kernel/` that discovers, reads, and parses a repository once and
  builds `ModuleFact`, `ImportBindingFact`, `FunctionFact`, `ClassFact`, `CommentFact`, and
  `CallFact`. It builds only the families the selected rules read, which is the whole dependency
  injection system: a rule cannot receive evidence it did not ask for.
- `mcmr check`, which runs the catalog over a repository through the kernel. MCMR's own source is
  324 files, 2,662 facts in 23 ms, and 24,986 rule invocations in 62 ms.
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
- Fixes are rewrite programs over resolved nodes. `Remove`, `Replace`, `Move`, `Unwrap`, and
  `Rename` each expose the spans they touch, so the engine detects conflicting fixes without
  knowing any rule, and a fix is testable without a provider. `docs/autofix.md` states the contract
  the language backend fulfills, including import management, atomic application, reparse, and
  re-running the rule before an edit is kept.
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
  over 389 messages, Ruff reads 34 of 968 generalized, and Clippy 10 of 809.
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
  Everything downstream now reads TypeScript: `ModuleCouplingFact` and so `ALL-ARCH0012` through
  `ALL-ARCH0014`, `OverrideFact`, `SymbolReachFact`, the class and package diagrams, the design
  structure matrix, and the impact set. On a 113-file SvelteKit project this is 2,144 nodes and
  4,945 edges where there were 180 and 179.
- `tests/test_fact_variation.py`, which finds a fact field a provider never varies. It builds every
  family over this repository and over a small written project stating the shapes this one lacks,
  and holds every field that never moves to a ledger with the reason, failing in both directions so
  a newly frozen field and a stale entry each turn the suite red. It records 160 fields and three
  families today, tells apart a field no frontend writes, a literal every frontend states, and a
  field the corpus simply never moves, and it found one more unsatisfiable rule in `PY-COLL0002`.
- A registry of works in `src/mcmr/data/works.json` and an influence table derived from it. Every
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
  `ALL-FUNC0015` reported 35 reflective scope reads on cuCollections, all false, and they are gone.
  The Rust frontend had the same defect and it is closed the same way.
- `kernel/src/interop.rs` read a CUDA artifact as the word following `__global__`, so the complete
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
- `ALL-COMM0002` failed all 206 files of cuCollections on the Apache notice each of them opens
  with. A licence is the same words in every file of a project and says nothing about the file, so
  it is left out of the measurement and the rule reports 51.
- `ALL-SECU0010` read any operator on a launcher's first argument as a command line assembled from
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
  questions about every module at once, so `kernel/src/classes.rs` reads the repository once and
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
  said in their own definitions, and `ALL-CLAS0002` no longer refuses to sort a class holding a
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
  `PY-TEST0016` 204, `PY-TEST0021` 127, `PY-TEST0011` 71, `PY-TEST0022` 15 and `PY-ENUM0002` 9,
  and over `aizk` `PY-TEST0017` reports 100 calls to `asyncio.run` inside a synchronous test.
- The differential oracle compared file paths where it claimed to compare findings. The
  `protected-access` case asserted that both readers named `generated.py`, which is true of any
  answer on a one-file tree, and the work-marker case compared fact spans that all start at line
  one. Both now compare the findings themselves, and every count-against-count assertion in the
  Ruff and Pylint oracles compares the lines or the declarations instead.

### Changed

- Kernel fact streams validate concurrently by family on the free-threaded Python build. Mainboard
  measured the stage at 2.20 to 2.34 seconds sequentially and 1.64 to 1.76 seconds by family under
  the regular interpreter. On MCMR's GIL-free environment three bounded runs moved from 584 to 792
  milliseconds sequentially to 462 to 473 milliseconds concurrently. Per-item threading and a
  fresh asynchronous event loop were both slower and are not used.
- Provenance is stated on the rule and the coverage of any tool is derived from it, rather than
  maintained by hand in a table beside it. Each of the 277 rules names the upstream rules it
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

- A fix returns the rewrites it wants rather than a plan. The framework decides whether those
  rewrites amount to one, and the fix's own first line of documentation is the summary, which
  removed the `plan` and `removal` helpers, the empty check every fix repeated, and the summary
  each one restated. The `Insert` operation went with them: nothing ever used it, and MCMR found it
  in its own source once a type reference became an edge.
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
- The rule engine runs on bounded AnyIO workers instead of one serial loop. Facts are grouped into
  chunks so a thread handoff costs less than the work it carries, validation and result
  construction happen in the worker beside the rule, and the worker count follows whether the
  interpreter still holds the GIL. A 43,200-invocation workload went from 605 ms to 86 ms.
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

- `mcmr/pylint.py` and the `mcmr ledger` command, replaced by `mcmr/upstream.py` and
  `mcmr coverage`. A module named after one tool was the wrong shape for an engine that fronts six
  languages and generalizes patterns from Pylint, Ruff, Clippy, clang-tidy, and SonarSource alike.

- Provider-precomputed fix candidates on facts, and the `fix_plan` lookup that retrieved them by
  name.
