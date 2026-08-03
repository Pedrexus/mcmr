# Rule backlog

What MCMR should own next, and why each item is not already owned by a narrower tool. The rule is
the same in every case: MCMR adds a rule only when it needs repository aggregation, a project
preference, runtime evidence, or a semantic decision the narrow tool does not make.

## Zero issue convergence

The 2026-07-31 deterministic self-scan is the convergence baseline. It reads 594 files and 28,283
facts, executes 185 of 209 selected deterministic rules, skips 24, and reports 3,022 failures with
3,958 findings. The kernel takes 1.68 seconds and the rule engine takes 1.12 seconds. The complete
machine report is an ephemeral run artifact rather than repository state.

Zero means more than hiding every diagnostic. Every applicable selected rule executes, no provider
is missing, no observation is unassessed, and no finding fails the project policy. A rule whose
premise is wrong is repaired or retired. A true finding changes the code. Configuration does not
silence either one.

Work proceeds through the following gates.

1. Freeze one JSON baseline and group failures by rule, source area, and shared fact. Re-run the
   selected rule after every bounded edit batch. A complete deterministic scan closes each phase.
2. Prove the largest rule before editing hundreds of sites. Inspect positive and negative examples,
   add one regression fixture for every false-positive shape, and repair the provider or rule at the
   first boundary that invented the answer.
3. Repair structure from the outside inward. Directory, module, and class ownership land before
   function extraction. Function size, statement count, and complexity land before signature and
   naming cleanup. Duplication lands after boundaries stop moving. Documentation and collection
   spelling land last.
4. Keep each batch mechanically reviewable. Select one rule or one source area, preview safe fixes,
   apply only verified plans, run lint and type checks, then compare its failure count with the
   frozen baseline. A batch never trades one family for a larger regression in another.
5. Eliminate skipped work explicitly. Rules for languages absent from the repository leave the
   selected scope instead of reading as skipped. The remaining provider-backed rules either gain
   their fact source or are retired with their replacement rationale.
6. Make contextual execution finite before calling it a full scan. Each contextual rule needs a
   rule-specific candidate projection, a reviewed positive and negative corpus, bounded batch
   requests, a declared token and turn budget, and provider coverage. The scan fails before model
   execution when its estimated workload exceeds that budget.
7. Finish with the complete deterministic scan, contextual corpus experiment, live
   contextual scan, upstream oracles, Python coverage, Rust tests, lint, type checks, and package
   build. The release candidate reaches zero without ignores, waivers, cache state, or hidden local
   evidence.

The first ten deterministic families account for 2,324 of the 3,022 failures. They are function
implementation lines, function statements, pasted blocks, swappable parameters, shallow public
callables, file-local public declarations, house docstrings, explicit tuple construction, class
method order, and multiple classes per module. This is the first trust and repair queue because it
removes 77 percent of the current failures while exposing interactions early.

The actual contextual repository workload is not ready for unattended execution. Twelve rules have
local providers and would create 13,433 isolated Codex turns over about 99.6 million subject
characters. Fifty-one contextual rules lack providers. Until candidate projections, batching, and
budgets land, `model-sweep` is the complete 65-rule contract check and a fixed representative
repository sample is the honest runtime probe. Neither substitutes for semantic corpus accuracy.

## Ownership boundary

| Concern | Owner | MCMR position |
| --- | --- | --- |
| Python syntax, modernization, unused imports and locals | Ruff | Never duplicate |
| Type correctness and inference | ty, Pyrefly | Never turn type status into an opinion |
| Branch-sensitive async control flow | flake8-async | Delegate, keep project policy rules |
| Rust local correctness and idiom | Clippy | Mirror only the design-level lints as general rules |
| TypeScript type-aware lint | typescript-eslint | Mirror only the design-level rules |
| C++ local checks and modernization | clang-tidy | Mirror only the design-level checks |
| CUDA guidance | nobody | MCMR can own it, no upstream lint does |
| Clone detection | jscpd, PMD CPD | Consume locations, decide shared knowledge separately |

## Landed in this pass

`ALL-FUNC0008` cognitive complexity, `ALL-FUNC0009` nesting depth, `ALL-FUNC0010` required
parameter count, `ALL-PARA0001` swappable parameter pair, `ALL-PARA0002` configuration object
parameter, `ALL-BRAN0001` value dispatch candidate, `ALL-CALL0001` unchecked result call,
`ALL-CALL0002` unbounded blocking call, `ALL-COMM0002` commented-out code, `CU-MEMO0001`
synchronous transfer in stream scope, `CU-LAUN0001` raw barrier over Cooperative Groups.

Cognitive complexity is the proof that one rule can answer for every language. SonarSource,
clang-tidy, and Clippy each carry their own implementation of the same measure; here the provider
supplies nesting-annotated control increments and the rule owns the scoring model, so one
definition serves them all.

That was a claim before it was a fact. `FunctionFact.control_increments` was filled by the Python
frontend and by nothing else, so the same nested function scored 16 for Python and 0 for Rust,
TypeScript, and C++, across 9,912 Rust and 227 TypeScript functions. A rule reporting zero reads
exactly like a clean repository, and the coverage test compared fact **families** rather than
fields, so nothing in the suite could tell the two apart. The Rust and TypeScript frontends filled
it first, through the reference frontend's own vocabulary and depth arithmetic. The native
frontend now records the same increments too, and an executable clang-tidy comparison holds the
shared cognitive score to the upstream implementation. `tests/test_language_coverage.py` keeps
the provider half honest and the rule property sweep keeps the arithmetic half honest.

## Landed in the design-measure pass

`ALL-CLAS0003` public method count, `ALL-CLAS0004` declared field count, `ALL-CLAS0005` ancestor
count, `ALL-PARA0004` boolean parameter count, `ALL-MODU0003` module inception. `PY-FUNC0007` is
retired, since `ALL-PARA0003` and `ALL-PARA0004` answer the Boolean trap for every language and the
narrow rule read three fields no frontend fills.

Two claims this page used to make were wrong and are corrected below. `ancestor_depth` exists on
`ClassAnalysis` and no frontend has ever filled it, so the inheritance measure reads `OverrideFact`
instead, which is the only fact that resolves a chain across files. `field_count` counts what a
class body states and never what an initializer assigns to the receiver, which is empty for most
hand-written Python, so the field measure reads the resolved declarations in `SymbolReachFact`.

## Next, ranked

### General, from the cross-language catalogs

1. ~~**Class surface size**~~, landed as `ALL-CLAS0003` over `ClassFact` and `ALL-CLAS0004` over
   `SymbolReachFact`. `struct_excessive_bools` is still open, since no fact carries the declared
   type of a field.
2. ~~**Inheritance depth**~~, landed as `ALL-CLAS0005` over `OverrideFact`, reported once per class
   at the link to its first declared base.
3. ~~**Boolean parameter count**~~, landed as `ALL-PARA0004`, counting every flag whatever its
   position, where `ALL-PARA0003` counts only the ones a caller cannot name.
4. **Large value passed by copy**, a parameter whose type exceeds a size budget. Clippy
   `large_types_passed_by_value`, clang-tidy `performance-unnecessary-value-param`.
5. **Wildcard import**, and its wildcard match sibling. Clippy `wildcard_imports`,
   `wildcard_enum_match_arm`.
6. ~~**Module inception**~~, landed as `ALL-MODU0003`, read from the file layout rather than from
   declarations, so a module a language nests inside another in one file is still out of reach.
7. **Similar identifiers in one scope**, names that differ by one character. Clippy
   `similar_names`, Pylint duplicate-code adjacent.
8. **Unhandled result contract on a public boundary**, an exported callable whose failure mode is
   undocumented. Clippy `missing_errors_doc`, `missing_panics_doc`.
9. **Member ordering**, already `ALL-CLAS0001`, extend to fields. Blocked on the kernel rather than
   on the rule: `MethodAnalysis` carries ordering by list position, every frontend fills that list
   from callables alone, and `MemberKind.FIELD` is a vocabulary entry nothing emits. Fields need to
   arrive in the same ordered member list before the rule can sort them.

### General, from the house rules

10. **Hand-rolled registry or dispatch table**, a literal mapping of names to callables used for
    selection, where `patos.Registry` or `value_dispatch` exists.
11. **Task runner bypass**, a repository-owned script or workflow calling `pip`, `pytest`, or
    `pixi` directly where chefe owns the task.
12. **Prose punctuation policy**, em dash, colon, and semicolon in comments and documentation.
13. **Defensive import guard**, a `try` around an import with a fallback, where the house policy is
    to assume the dependency is present.
14. **Broad exception handler outside an entry point**, which is the house nuance Ruff `BLE001`
    does not model.

### Python

15. **SQLAlchemy declarative API inside a SQLModel project**, `declarative_base`, `mapped_column`,
    `sessionmaker`, and `Mapped[...]`, from the sqlmodel skill.
16. **Runtime async evidence**, never-awaited coroutines, never-retrieved task exceptions, slow
    callbacks, and leaked tasks, normalized from the Python 3.14 debug records rather than
    instrumented here.

### CUDA and C++

17. **Host round trip inside a device pipeline**, a device-to-host copy feeding host control flow
    between two kernels.
18. **Two-phase CUB temp storage**, where the CUDA 13.1 single-call API removes the boilerplate.
19. **Block size that is not a multiple of the warp**, from a launch configuration with literal
    dimensions.
20. **Missing launch error check**, no `cudaGetLastError` after a launch in the same scope.
21. **Special member functions**, the rule of five. clang-tidy
    `cppcoreguidelines-special-member-functions`.
22. **Const correctness**, a member function or parameter that never mutates. clang-tidy
    `misc-const-correctness`, `readability-make-member-function-const`.

### TypeScript and Rust, once a frontend exists

23. **Floating promise**, a promise-returning call whose result is discarded. This is
    `ALL-CALL0001` with a configured contract, so it needs a frontend rather than a new rule.
24. **Unnecessary condition**, a test whose type makes it always true or always false. Needs the
    optional semantic stage.
25. **Needless pass by value**, a parameter consumed only by reference. Clippy
    `needless_pass_by_value`.
26. **Large enum variant and large error type**, layout costs a caller pays silently. Clippy
    `large_enum_variant`, `result_large_err`.
27. **The input arity a lifetime elides against**, which `RS-LIFE0001` needs to settle its third
    arrangement. An output lifetime coming from one input with no receiver is elidable exactly when
    the inputs hold one lifetime position in total, and a path type written without its lifetime
    arguments hides one, so the count lives in the type definitions rather than in the signature.
    Clippy reads them and reports the arrangement; MCMR declines it, which is the one difference
    `tests/test_clippy_oracle.py` pins.

### Frontend gaps a general rule already reads

These are not new rules. Each is a rule that exists, answers for the reference language, and
answers zero somewhere else because a frontend does not fill what it reads. Every one is recorded
in the ledger of `tests/test_language_parity.py`, so the list here and the ledger there cannot
drift apart.

28. **`CommentFact` from the TypeScript frontend**, which `ALL-COMM0001`, `ALL-COMM0002`, and
    `ALL-COMM0003` read. `SyntaxFact` and native control increments landed, leaving comments as the
    provider gap in this group.
29. **A qualified name is not always dotted.** `ALL-CLAS0005` compares the last component of a
    resolved base, split on `.`, against the name the source wrote, so `crate::sample::Base` never
    matches `Base` and the ancestor count is zero for every language but Python. The comparison
    wants the separator the language uses, or a base name the fact states directly.

### Upstream accounts

The ESLint, typescript-eslint, clang-tidy, and cppcheck inventories have landed. Their gap files
account for all 1,372 rules, and the tool profiles make their language boundaries part of the
coverage decision. The three ESLint claims backed by `SyntaxFact` now have direct executable
comparisons.

## Facts these need

Most of the backlog needs no new fact family. The ones that do:

* a `LaunchFact` for kernel configuration, carrying literal grid and block dimensions and the
  stream a launch names
* a `ScopeFact` for declarations visible together, which the similar-names and registry rules read
* an `EdgeFact` for resolved data movement, which the host round trip rule reads
* `ControlIncrement` extended with the Boolean-operator sequence, so cognitive complexity scores
  mixed operators the way the published model does
* `MethodAnalysis` extended to carry data members beside callables, which member ordering needs
  before it can sort fields and which `struct_excessive_bools` needs for the declared type of each
