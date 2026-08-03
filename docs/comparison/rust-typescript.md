# MCMR against the Rust and TypeScript toolchains

What MCMR can and cannot know about a Rust crate or a TypeScript project, measured against the
tools people actually run, on real corpora, with every number attached to a command.

The measurements below preserve the state observed at the start of 2026-07-27. The follow-up fixed
the provider and provenance defects they exposed. TypeScript now fills `SyntaxFact`, native code
fills control increments, and the ESLint and typescript-eslint inventories are part of the checked
reference table.

## What MCMR is for, and where it does not compete

MCMR judges a repository rather than a file. Its premise is that the interesting questions about a
codebase are aggregate ones. How far a declaration's use spreads, which module everything leans on,
whether one abstraction has drifted, which folder holds more modules than a reader can hold in
mind, whether the shape of the code moved in the right direction since the last recorded run. Those
questions need the whole tree and a graph over it, and no single-file linter is built to answer
them.

Three things follow, and each is a place MCMR deliberately does not compete.

MCMR does not format. rustfmt, Prettier, and the formatter halves of Biome and Ruff own that
entirely, MCMR ships no formatting rule and never will, and nothing below compares against them
again.

MCMR does not type check. It has no type inference, no borrow checker, no module resolution beyond
what a lexical reader plus an import graph can settle. Every judgment that turns on an inferred
type belongs to `tsc`, to `rustc`, and to the type-aware half of typescript-eslint.

MCMR does not chase local idiom. `docs/backlog.md` states the boundary already, that Clippy owns
Rust local correctness and idiom and typescript-eslint owns TypeScript type-aware lint, and that
MCMR mirrors only the design-level rules. That boundary is correct and this document does not argue
with it.

What this document does argue with is the gap between that stated boundary and what the catalog
currently delivers for these two languages, which is much wider than the catalog reads.

## How every number here was produced

Versions, read from the installed tools on 2026-07-27.

| Tool | Version | How it was read |
| --- | --- | --- |
| MCMR | 0.0.1, working tree, no commits | `pyproject.toml` |
| rustc, cargo | 1.96.1 | `rustc --version` |
| Clippy | ships with 1.96.1 | `clippy-driver -W help -` |
| cargo-audit | latest from crates.io | `cargo install cargo-audit --root /tmp/cargo-tools` |
| cargo-geiger | latest from crates.io | same |
| cargo-machete | latest from crates.io | same |
| ESLint | 10.8.0 | `npm install` into `/tmp/tsjudge` |
| typescript-eslint | 8.65.0 | `npm install` into `/tmp/tsjudge6` |
| TypeScript | 7.0.2 and 6.0.3 | both, see below |
| Biome | 2.5.5 | `/tmp/tsjudge` |
| oxlint | 1.75.0 | `/tmp/tsjudge` |
| eslint-plugin-import | 2.32.0 | `/tmp/tsjudge` |
| eslint-plugin-unicorn | 72.0.0 | `/tmp/tsjudge` |
| eslint-plugin-security | 4.0.1 | `/tmp/tsjudge` |
| eslint-plugin-sonarjs | 4.2.0 | `/tmp/tsjudge6` |
| knip | 6.29.0 | `/tmp/tsjudge` |
| ts-prune | 0.10.3 | `/tmp/tsjudge` |
| dependency-cruiser | 18.1.0 | `/tmp/tsjudge6` |
| madge | 8.0.0 | `/tmp/tsjudge6` |
| type-coverage | latest from npm | `/tmp/tsjudge6` |

Two corpora, both real code nobody wrote to satisfy a rule.

**Rust.** Five widely used crates copied out of the local cargo registry, `tokio-1.53.1`,
`syn-2.0.119`, `regex-1.13.1`, `clap-4.6.4`, and `rayon-1.12.0`, which is 875 `.rs` files and
8.1 MB. A second copy holds only the 824 files that are pure ASCII, for the reason given under
"the crash" below. Plus MCMR's own core crate under `src/core/src`, which is the one
Rust codebase where a head-to-head against Clippy on identical source is possible.

**TypeScript.** Two real SvelteKit and Cloudflare Workers projects, `personal/my` and
`packages/aizk/src/web`, which is 174 `.ts` files beside 197 `.svelte` components. Most head-to-head
numbers use `personal/my/src` alone, which is 111 `.ts` files beside 146 `.svelte` components,
because that is where every tool can be pointed at the same target.

One caveat on TypeScript tooling that bit during this work and is worth stating. TypeScript 7.0 is
the native port and typescript-eslint refuses to load against it, asking for the TypeScript 6 API
side by side, and dependency-cruiser refuses too, wanting `typescript >=2.0.0 <7.0.0`. Both were
measured against TypeScript 6.0.3 in a separate sandbox. Anything that reads the TypeScript
compiler API is currently pinned behind the 7.0 release.

Claims marked *documented* below come from a tool's own documentation because the tool was not
installed here. Everything else was run.

## The dividing line is evidence, not rule count

A rule count is close to meaningless as a headline. Clippy ships 809 lints, ESLint core plus
typescript-eslint, SonarJS, unicorn, import, and security ships 1,106, and MCMR ships 279 across six
languages. Those three numbers answer different questions and comparing them says nothing.

What matters is what each tool can know. Here is the real ladder, measured where a command settles
it.

| Evidence | Clippy and rustc | typescript-eslint type-aware | tsc | oxlint, Biome, ESLint core | MCMR |
| --- | --- | --- | --- | --- | --- |
| One file's tokens | yes | yes | yes | yes | yes |
| One file's AST | yes | yes | yes | yes | yes, through `SyntaxFact` for Python, Rust, C, C++, CUDA |
| Resolved imports across the project | yes | yes | yes | partly | yes, through the repository graph |
| Inferred types | yes, fully type-checked HIR | yes, whole TypeScript program | yes | no | **no** |
| Borrow and lifetime facts | yes | not applicable | not applicable | no | **no** |
| Whole-crate or whole-program view | yes | yes | yes | no | yes |
| Dependency manifest and lockfile | yes, and cargo-audit, cargo-deny read the lockfile | no | no | no | partly, the manifest only |
| Dependency source code | cargo-geiger reads the whole tree | no | through `.d.ts` | no | **no** |
| Git history | no | no | no | no | yes |
| Two points in time | cargo-semver-checks, over two published API snapshots | no | no | no | no, checks are stateless |
| Runtime behavior | Miri, under interpretation | no | no | no | no |

Clippy sees a fully type-checked HIR. That is a genuine and very large advantage, and it is the
single most important sentence in this document. Clippy knows that a value is a `Vec`, that a
method resolves to `Iterator::map`, that a type is `Copy`, that a borrow outlives a scope. MCMR
knows none of that and no amount of rule authoring will change it, because the evidence is not in
the fact contract.

typescript-eslint's type-aware rules need a full TypeScript program, and of its 134 rules, 61 are
marked `requiresTypeChecking`. Those 61 are unreachable for MCMR for the same reason.

```sh
# rule inventories, re-runnable
clippy-driver -W help - < /dev/null
node -e "const {builtinRules}=require('eslint/use-at-your-own-risk'); console.log(builtinRules.size)"
oxlint -D all -D nursery --import-plugin --react-plugin --print-config
```

## Rust

### The field, grounded

`clippy-driver -W help -` answers on an empty source, so the whole inventory reads without
compiling anything.

| Source | Lints | Default level |
| --- | --- | --- |
| rustc itself, through clippy-driver | 241 | 61 allow, 134 warn, 46 deny |
| Clippy | 809 | 327 allow, 414 warn, 68 deny |

Clippy's groups, from the same output.

| Group | Lints | On by default |
| --- | --- | --- |
| correctness | 68 | yes, deny |
| suspicious | 82 | yes, warn |
| style | 157 | yes, warn |
| complexity | 139 | yes, warn |
| perf | 36 | yes, warn |
| pedantic | 140 | no |
| nursery | 52 | no |
| restriction | 130 | no, and never as a group |
| cargo | 5 | no |

The 482 lints of `clippy::all` run on every `cargo clippy` invocation with no configuration. That
is the baseline any Rust project already has for free, and it is the number MCMR is actually
competing against, not 809.

The rest of the Rust field, each answering something Clippy does not.

| Tool | What it knows that nothing else does | Status here |
| --- | --- | --- |
| **cargo-audit** | the lockfile against the RustSec advisory database | run, 1,169 advisories loaded, 180 dependencies scanned, 0.49 s, no vulnerabilities in the kernel |
| **cargo-deny** | licences, banned crates, duplicate versions, allowed sources, plus advisories | *documented*, four independent checks stated as a `deny.toml` contract |
| **cargo-geiger** | `unsafe` usage across the entire dependency tree, not just your crate | run, 9.1 s, reports 161/221 unsafe functions and 17,574/20,224 unsafe expressions reachable from the kernel |
| **cargo-udeps** | declared dependencies never linked, using real compiler output | *documented*, needs a nightly toolchain |
| **cargo-machete** | declared dependencies never named in source, lexically | run, 0.02 s, no unused dependencies in the kernel |
| **cargo-semver-checks** | whether a version bump breaks the public API, by comparing two rustdoc JSON snapshots | *documented* |
| **rust-analyzer** | the same semantic model as rustc, incrementally, in the editor | *documented*, its diagnostics are the type errors and a small set of assists |
| **Miri** | undefined behavior under an interpreter, which is runtime rather than static | *documented*, it executes the test suite |
| **dylint** | your own Clippy-style lints, written in Rust, against the same HIR Clippy sees | *documented*, and the single most direct competitor to MCMR's premise for Rust |

dylint deserves the emphasis. MCMR's pitch is that a project should be able to state its own rules.
dylint already lets a Rust project do exactly that, with the full type-checked HIR underneath, and
Clippy itself ships `disallowed_methods`, `disallowed_types`, `disallowed_macros`,
`disallowed_names`, and `disallowed_fields`, each configured from a `clippy.toml` that a project
owns. A Rust team that wants project-specific policy already has two supported routes with strictly
more evidence than MCMR can offer.

### What MCMR actually does on Rust, measured

The catalog is 279 rules. Five are `RS-` scoped and 116 are general and deterministic, so 121 rules
are eligible for a Rust repository.

```sh
mcmr check /tmp/.../rust-ascii --suffixes .rs --format concise
```

Over the 824-file ASCII corpus.

| State | Rules |
| --- | --- |
| the family the rule reads is non-empty | 69 general, plus all 5 Rust rules |
| the family is built but empty for Rust | 17 |
| the family had no source or provider implementation in this measurement | 30 |
| ran on real evidence and never returned anything but zero | 38 |
| returned a non-zero value at least once | 36 |
| failed the then-current default policy at least once | 34 distinct rules, 5,811 failures, 22,292 findings |

Those 17 rules read eleven families the Rust frontend does not fill, which are
`AttributeAccessFact`, `BranchFact`, `DependencyComponentFact`, `InteropFact`, `LiteralGroupFact`,
`MethodGroupFact`, `ParameterFact`, `ProseSegmentFact`, `RepositoryHistoryFact`,
`StringExpressionFact`, and `WaiverFact`. `RepositoryHistoryFact` is empty only because the corpus
is not a git checkout.

Running MCMR's own fact-variation analysis over the corpus, the same one
`tests/test_fact_variation.py` performs on MCMR's Python, says how thin the filled families are.
**130 of the 254 fact fields the Rust corpus can reach never take a second value across 875 files.**
`FunctionFact` alone contributes 39 of those, `ClassFact` 28.

### The crash

`mcmr check` on the unmodified five-crate corpus does not produce a report. It dies.

```
thread '<unnamed>' panicked at src/rust.rs:112:25:
start byte index 5748 is not a char boundary; it is inside '🐕'
```

The lexical comment scanner in `src/core/src/rust.rs` advances one byte at a time and then slices
`&text[at..]`, which panics on any multi-byte UTF-8 character it steps onto. Probed with minimal
fixtures, a non-ASCII character panics the whole kernel run when it sits in a `char` literal, inside
a block comment, or inside an identifier. Line comments and string literals are safe because the
scanner jumps over them.

51 of the 875 corpus files hold a non-ASCII byte, and four of the five crates contain one. One such
file anywhere in a repository takes down the entire analysis, for every family, not just the comment
family. This is the first thing a Rust user would hit and it is a hard stop.

```sh
# reproduces in four lines
printf 'pub fn a() { let c = %s; }\n' "'\xf0\x9f\x90\x95'" > /tmp/rs-min/a.rs
echo '{"families":["CommentFact"],"suffixes":[".rs"],"root":"/tmp/rs-min"}' | mcmr-kernel
```

### Head to head on identical source

MCMR's own kernel is 24 files and 21,143 lines of Rust, and the repository gates it on
`cargo clippy -- -D warnings`, so default Clippy is clean by construction.

| Tool | Wall, best of 3 | Findings |
| --- | --- | --- |
| `cargo check` | 0.25 s | compiles |
| `cargo clippy`, default 482 lints | 0.60 s | 0 |
| `cargo clippy -W clippy::pedantic -W clippy::nursery` | 0.87 s | 218 warnings, 169 machine-applicable |
| `cargo-machete` | 0.02 s | 0 |
| `cargo-audit` | 0.49 s | 0 |
| `cargo-geiger` | 9.1 s | whole-tree unsafe census |
| `mcmr check src/core/src --suffixes .rs` | 0.99 s | 360 failures, 340 findings, 22 distinct rules |

The overlap in kind is close to nil, and that is the honest headline. Clippy's 218 are idiom and API
shape, `map(f).unwrap_or(a)`, `this could be a const fn`, `casting usize to u32 may truncate`,
`redundant clone`. MCMR's 340 are duplication, swappable parameter pairs, uninformative local names,
declarations nothing reaches, class member ordering, module coupling, and lifetime counts. A project
running both gets two disjoint reports, which is the strongest argument for MCMR sitting beside
Clippy rather than under it.

### The Rust rules, tested one at a time

MCMR ships five Rust rules. Here is what each does on the kernel, and what a comparable tool says
about the same source.

**`RS-LIFE0001` elidable lifetime annotation reports 13 sites on the kernel, and all 13 are wrong.**

Its own docstring states the exception it needs. "A trait or type that names a lifetime is not
judged here at all, since neither has an elision rule to compare against." The implementation never
checks `annotation.kind`, so `type`, `alias`, and `trait` declarations fall straight through
`if not returned: return True` and are counted. Ten of the 13 sites are exactly that.

The other three are functions where the lifetime never reaches the output, which the rule treats as
always elidable. That reasoning holds only when the lifetime occupies one input position. Here it
occupies two that must unify, and elision would give them separate lifetimes.

Proven rather than argued. Take the two shapes the rule flags, remove the annotations it calls
redundant, and the crate stops compiling.

```rust
pub struct Repository { pub names: Vec<&str> }              // E0106 missing lifetime specifier
pub fn descend(expression: &str, found: &mut Vec<&str>) {   // lifetime may not live long enough
    found.push(expression);
}
```

Clippy is silent on the originals, correctly. Its `needless_lifetimes` lint is in the `complexity`
group, which is on by default, so any real elidable lifetime would already have been reported with
its exact span and a machine-applicable fix. On the 824-file corpus `RS-LIFE0001` fires 110 times,
and there is no reason to expect a better hit rate there.

`RS-LIFE0002`, `RS-LIFE0003`, `RS-OWNE0001`, and `RS-OWNE0002` are measurements rather than defect
reports and are more defensible as a pair of ceilings. `RS-OWNE0002` maps to Clippy's
`redundant_clone`, which is a nursery lint and off by default, so MCMR is genuinely adding something
a default Clippy run does not report. But `redundant_clone` names the exact `.clone()` and offers
`help: remove this`, and `RS-OWNE0002` reports `graph.rs` and the number 55.

**Every one of the five Rust rules produces zero findings.**

```
$ mcmr check src/core/src --suffixes .rs --select rust.deterministic.lifetimes
classes.rs:1:1: RS-LIFE0001 Count lifetime annotations the compiler would have inferred on its own. (2, allowed <= 0)
...
24 files, 24 facts, 72 invocations, 9 failures, 0 findings, 0 unassessed
```

A file and a number. No line, no name, no snippet. A reader cannot act on that without redoing the
analysis by hand, and an agent cannot act on it at all. Across the whole kernel run, only 7 of the
22 failing rules point at a real line, and none of them is a Rust rule.

### The Clippy coverage account overstates by two

`mcmr coverage --tool clippy` reports 10 native and 799 delegated over 809 lints. Cross-checking each
of the 10 native claims against a real Rust corpus.

| Clippy lint | MCMR rule | Does it answer for Rust |
| --- | --- | --- |
| `too_many_arguments` | `ALL-FUNC0010` | yes, 4,863 non-zero over the corpus |
| `let_underscore_must_use` | `ALL-ERRO0001` | yes, 78 failures |
| `fn_params_excessive_bools` | `ALL-PARA0004` | yes, 73 non-zero |
| `dbg_macro`, `print_stdout` | `ALL-CONT0003` | yes |
| `module_inception` | `ALL-MODU0003` | yes |
| `redundant_clone` | `RS-OWNE0002` | yes, 189 non-zero |
| `excessive_nesting` | `ALL-CONT0004` and `ALL-FUNC0009` | partly, `ALL-CONT0004` answers and `ALL-FUNC0009` cannot |
| `cognitive_complexity` | `ALL-FUNC0008` | **no**, always zero on Rust |
| `no_effect` | `ALL-CONT0002` | **no**, the rule's own docstring says it "answers for Python and waits on the others" |

So the real figure is 8 of 809, not 10. `ALL-CONT0002` is the sharper case, because the rule is
honest in prose and the account still records a native claim. `tests/test_upstream_coverage.py`
checks that a Python message names a rule whose scope could answer one, and nothing performs the
equivalent check for a Rust lint claimed by a general rule that cannot read Rust evidence.

Demonstrated on the exact program Clippy flags.

```rust
pub fn wasteful(a: i32, b: i32) -> i32 { a + b; let total = a * b; total }
```

```
cargo clippy   a.rs:2:5: warning: statement with no effect
mcmr           statement_without_effect(fact) == 0
```

## TypeScript and JavaScript

### The field, grounded

Every count below came from loading the plugin and reading `meta` off each rule.

| Tool | Rules | Fixable | Suggestions | Need type info |
| --- | --- | --- | --- | --- |
| ESLint core | 292, of which 93 deprecated | 106 | 30 | 0 |
| typescript-eslint | 134 | 46 | 39 | **61** |
| eslint-plugin-sonarjs | 279, of which 13 deprecated | 3 | 36 | 70 |
| eslint-plugin-unicorn | 341 | 200 | 128 | 1 |
| eslint-plugin-import | 46 | 13 | 2 | 0 |
| eslint-plugin-security | 14 | 0 | 0 | 0 |
| oxlint | 844 across 15 plugins, 452 with the default plugin set | `--fix`, `--fix-suggestions`, `--fix-dangerously` | | 0 |
| Biome | 518 across 8 groups, 84 of them nursery | `--write`, `--unsafe` | | 0 |
| tsc | 139 compiler options, 24 of them type-checking behavior | not applicable | | it *is* the type info |

`strict` alone turns on eight of those 24 flags, and `noUncheckedIndexedAccess`,
`exactOptionalPropertyTypes`, `noPropertyAccessFromIndexSignature`, and `erasableSyntaxOnly` are
separate switches a project opts into. Turning on `strict` is the single highest-leverage lint
decision a TypeScript project makes, and no linter substitutes for it.

The project-shape tools, which are where MCMR's questions actually live.

| Tool | What it states | Contract |
| --- | --- | --- |
| **knip** | unused files, exports, types, dependencies, and devDependencies, framework-aware | derived from entry points, configurable |
| **ts-prune** | unused exports | derived, **last published 2022-05-22, effectively abandoned, its own repository points at knip** |
| **dependency-cruiser** | forbidden dependency edges, orphans, cycles, layering | stated as a config file |
| **madge** | circular dependencies and a graph image | derived |
| **type-coverage** | share of identifiers with a non-`any` type, and names every one that is not | derived, reads the type checker |
| **eslint-plugin-import** | import correctness, cycles, ordering, and `no-restricted-paths` layering | layering stated as config |
| **ast-grep** | structural search and rewrite rules across many languages | stated as YAML patterns |
| **eslint-plugin-boundaries** | element types and the edges allowed between them | stated as config |
| **jscpd** | copy-paste detection across languages | derived |
| **svelte-check**, **vue-tsc** | type checking inside framework component files | derived |

type-coverage is worth naming twice, because it measures exactly what MCMR's `TS-TYPE0002` claims to
measure and it reads the type checker to do it.

```
$ type-coverage --detail -p tsconfig.json
(13773 / 13992) 98.43%
```

1.9 seconds, and it names every untyped identifier with a line and a column.

### What MCMR actually does on TypeScript, measured

Four `TS-` rules plus 116 general deterministic rules, so 120 are eligible.

```sh
mcmr check /home/pedro/projects/personal/my/src --suffixes .ts --format concise
```

| State | Rules |
| --- | --- |
| the family the rule reads is non-empty | 49 general, plus all 4 TypeScript rules |
| the family is built but empty for TypeScript | **37** |
| the family had no source or provider implementation in this measurement | 30 |
| ran on real evidence and never returned anything but zero | 26 |
| returned a non-zero value at least once | 27 |

**Thirty-seven of the 116 general rules read an empty stream on TypeScript.** Those 37 read fourteen
families the TypeScript frontend did not fill in that run, which were `AttributeAccessFact`, `BranchFact`,
`CallFact`, `CommentFact`, `DependencyComponentFact`, `InteropFact`, `LiteralGroupFact`,
`MethodGroupFact`, `ParameterFact`, `ProseSegmentFact`, `RepositoryHistoryFact`,
`StringExpressionFact`, `SyntaxFact`, and `WaiverFact`. `SyntaxFact` has since landed.

`SyntaxFact` was the expensive one. It carries 14 general rules on its own, the whole `ALL-CONT`,
`ALL-ERRO`, `ALL-SECU`, and `ALL-NAMI` families among them, and it is the family `docs/kernel.md`
describes under K2b as the one that reads code rather than counts. That K2b item is now complete. `CallFact` and
`CommentFact` are unfilled too, which takes out the work-marker rule, the commented-out-code rule,
the unchecked-result rule, and the unbounded-blocking-call rule.

Language coverage across all three, using the same command shape, so the shortfall is legible.

| | general rules with evidence | family built but empty | needs a record file |
| --- | --- | --- | --- |
| Python, MCMR's own 467 files | 83 | 3 | 30 |
| Rust, 824 crate files | 69 | 17 | 30 |
| TypeScript, 174 files | **49** | **37** | 30 |

The fact-variation analysis says the same thing one level down. **114 of the 220 fact fields the
TypeScript corpus can reach never take a second value.** `FunctionFact` contributes 41 and
`ClassFact` 29. Thirty-eight `FunctionFact` fields are frozen in both Rust and TypeScript, among
them `is_recursive`, `is_abstract`, `decorators`, `reference_count`, and `control_increments`.
Several of those are legitimately absent, since neither language has keyword-only parameters. Others
are not. TypeScript has decorators and the frontend does not record them, both languages have
recursion and neither frontend marks it, both have abstract members and neither frontend says so.
`FunctionFact` has 47 fields and it remains, in practice, a Python fact model.

### `TS-TYPE0002` escape hatch density is 86 percent false positives

This is the flagship TypeScript rule, the one whose `References` section claims to generalize
typescript-eslint `no-explicit-any` and `no-non-null-assertion`. The kernel finds its evidence
lexically.

```rust
if line.contains(" as ") && !line.trim_start().starts_with("//") {
    found.push(("assertion", line_number));
}
```

In TypeScript, `as` is the type assertion operator *and* the import and export rename keyword *and*
an ordinary English word. Classifying all 132 lines the rule counts as assertions across
`personal/my/src`.

| What the line actually is | Count |
| --- | --- |
| an import or export rename, `export { default as Badge }` | 95 |
| prose inside a JSDoc block, which the `//` guard does not catch | 10 |
| `as const`, which narrows a type rather than escaping it | 7 |
| an English `as` inside a string literal | 2 |
| **a real type assertion** | **18** |

114 of 132, or 86 percent, are not assertions. The failure mode is not random, it is systematic and
it targets barrel files. `src/lib/components/turnstile/index.ts` is one line long,
`export { default as TurnstileWidget } from './TurnstileWidget.svelte'`, and the rule reports
**100.0 percent escape hatch density**. `badge/index.ts` is two lines and reports 50.0. Run over the
whole project the rule fails at 37 sites, and 17 of those are generated SvelteKit type files.

The kernel already has the full oxc AST at the call site. One line above, `erasable_violations` is
built by a function that takes the parsed `Program` and walks it properly, while `escape_hatches`
is handed the raw text. The lexical shortcut is not forced by the evidence available.

The rule also renders unrounded floats, `5.633802816901409`, and produces no findings at all, so a
reader gets a percentage with no site.

### `TS-TYPE0001` is genuinely good, and has one clean hole

The counterexample is worth as much space, because this rule shows what MCMR can do without a type
checker. `tsc --erasableSyntaxOnly` is an exact oracle for it.

```sh
tsc --noEmit --erasableSyntaxOnly -p tsconfig.json
```

Over `personal/my/src`, tsc finds 13 sites in 8 files and MCMR finds 12. Every one of MCMR's 12
matches a tsc site exactly, on line and on construct, so precision is complete and recall is 12 of
13, in 3 ms of kernel time against tsc's 1.58 seconds.

The one miss has a clean cause. `erasable()` matches `Statement::TSEnumDeclaration` and
`Statement::TSModuleDeclaration` directly, and does not look through `Statement::ExportNamedDeclaration`
the way its neighbour `declared_class()` does. So `export enum` and `export namespace` are invisible.
Proven on a four-line fixture.

```typescript
export enum Exported { A = 'a' }              // tsc reports, MCMR misses
enum Local { B = 'b' }                        // both report
export namespace Wrapped { export const x = 1 }  // tsc reports, MCMR misses
namespace Plain { export const y = 2 }        // both report
```

Most enums in real TypeScript are exported, so this is a large recall hole behind a two-line fix.

Separately, MCMR reports six `declare namespace` sites in `.svelte-kit/*.d.ts` that tsc correctly
does not, because an ambient declaration is fully erasable. The rule's own `Exceptions` section
anticipates this and asks the project to exclude declaration files, which is fair, except that the
kernel's default exclusion set does not.

### Unused code, MCMR against knip

Both answer "what is dead here" and they disagree by a lot.

| Tool | Answer on `personal/my` | Wall |
| --- | --- | --- |
| knip | 10 unused files, 30 unused exports, 14 unused exported types, 4 unused devDependencies | 1.02 s |
| ts-prune | 544 unused exports in `src`, plus a flood from `.svelte-kit` | 0.76 s |
| MCMR `SymbolReachFact` | 304 unreached public declarations across 84 files, of which 120 are attributes and 71 methods | 0.49 s |

Narrowing MCMR's answer to the 90 module-level functions, classes, and variables, and grepping the
project's 146 `.svelte` components for each name, **42 of the 90 are referenced from a component**.
The match is textual and so it overcounts slightly, but the direction is not in doubt. MCMR reads
`.ts` and never `.svelte`, so anything a component consumes reads as unreached. knip parses Svelte
and gets this right.

MCMR does agree with knip on the clear cases. `createSupabaseClient`, `alignEntriesWithTokens`, and
the `dictionary/schema.ts` exports appear in both answers.

### Head to head on identical source

`personal/my/src`, 111 `.ts` files, best of three runs.

| Tool | Wall | Findings |
| --- | --- | --- |
| oxlint, correctness only | 0.08 s | 6 |
| oxlint, `-D all` | 0.09 s | 3,297 |
| Biome lint, recommended | 0.10 s | 551 |
| dependency-cruiser | 0.46 s | 6, against a three-rule contract |
| madge `--circular` | 0.55 s | 0 |
| ESLint, typescript-eslint recommended | 0.56 s | 11 |
| **mcmr check --suffixes .ts** | **0.63 s** | **183 failures, 108 findings, 19 rules** |
| knip | 1.02 s | 58 |
| tsc `--noEmit` | 1.58 s | 6 |
| type-coverage | 1.87 s | 98.43 percent, 219 untyped identifiers named |
| ESLint, recommendedTypeChecked, 47 rules | 2.69 s | 46 |

MCMR is competitive on wall time and it is answering different questions, which is the good news.
The bad news is in the column on the right. Of the 207 lines that report prints, only 40 point at a
real line and 167 point at line 1 column 1. Two of the 19 failing rules localise a finding, and
neither of them is a TypeScript rule.

The type-aware ESLint run is the one to study. Its 46 messages are `no-unsafe-assignment`,
`no-unnecessary-type-assertion`, `require-await`, `no-unsafe-return`, `unbound-method`,
`only-throw-error`. Every one of those needs the type checker, and every one is structurally out of
MCMR's reach forever.

### The ESLint coverage claims

MCMR's rule docstrings name eight ESLint and typescript-eslint rules. Both tools now have frozen
inventories and complete gap accounts in `mcmr/data/`, and the native claims below have executable
oracle comparisons.

| Claimed rule | MCMR rule | Answers for TypeScript |
| --- | --- | --- |
| typescript-eslint `max-params` | `ALL-FUNC0010` | yes |
| typescript-eslint `no-restricted-imports` | `TS-MODU0002` | adapted, not equivalent |
| typescript-eslint `no-explicit-any`, `no-non-null-assertion` | `TS-TYPE0002` | fires, 86 percent false positives |
| ESLint `no-unused-expressions` | `ALL-CONT0002` | yes, oracle checked |
| ESLint `no-console`, `no-debugger` | `ALL-CONT0003` | yes, oracle checked |
| ESLint `max-depth` | `ALL-FUNC0009` | yes |

All four previously inert ESLint claims now receive provider evidence. The restricted import rule
is recorded as adapted because it measures distance instead of enforcing a configured list.

## Testing the one-rule-many-languages claim

`docs/backlog.md` states it plainly.

> Cognitive complexity is the proof that one rule can answer for every language. SonarSource,
> clang-tidy, and Clippy each carry their own implementation of the same measure; here the provider
> supplies nesting-annotated control increments and the rule owns the scoring model, so one
> definition serves them all.

The same program, written four times, run through the same rule.

```
python      tangled    increments= 6  cognitive=16  nesting=4
rust        tangled    increments= 0  cognitive= 0  nesting=0
typescript  tangled    increments= 0  cognitive= 0  nesting=0
cpp         tangled    increments= 0  cognitive= 0  nesting=0
```

`FunctionFact.control_increments` is filled by the Python frontend and by nothing else. Over 9,912
Rust functions and 227 TypeScript functions in the corpora, not one carries a single control
increment. `ALL-FUNC0008` cognitive complexity and `ALL-FUNC0009` nesting depth therefore answer for
Python and return zero everywhere else, which is precisely the failure mode `docs/kernel.md` names
under K2d as the worst shape a rule can have. The backlog page states the opposite of what the code
does, and it is the load-bearing claim of the whole cross-language thesis.

Neither of the two honest-record tests catches this, and the reason is worth understanding because
it is the shape of the next such defect.

`tests/test_language_coverage.py` asks whether the *family* is filled. `FunctionFact` is filled for
Rust and TypeScript, so the test passes while the one field the rule reads stays empty.

`tests/test_fact_variation.py` asks whether a *field* ever moves, but its corpus is MCMR's own
Python plus a written Python fixture. `control_increments` varies over that corpus, so it never
enters the ledger. Neither test runs a non-Python corpus.

That said, the vocabulary claim is not empty. Three rules were verified to work identically across
languages from one definition, `ALL-NAMI0001` uninformative local names finding 803 sites in Rust,
`ALL-COMM0003` work markers finding 45, and `ALL-COMM0002` commented-out code finding 8. The
mechanism is real. What is not real is the specific rule the backlog nominates as its proof.

## Configuration, derived contract against stated contract

This is the axis where MCMR has the more interesting position, and it deserves both directions.

`dependency-cruiser` and `eslint-plugin-import`'s `no-restricted-paths` make a project write its
layering down.

```javascript
{ name: "features-not-to-lib-internals", severity: "error",
  from: { path: "^src/lib" }, to: { path: "^src/features" } }
```

`docs/kernel.md` argues against this under K2c, that a layering contract in a config file rots,
somebody adds a legitimate edge, the check fails, they widen the rule, and within a year the file
describes the code instead of constraining it. `ModuleCouplingFact` therefore derives Martin's
instability and abstractness every run, and `ALL-ARCH0003` reports an import pointing at a less
stable module without anyone naming a layer.

The argument is good and the counter-argument is equally good. A derived measure cannot express an
intention the code does not already hold. `dependency-cruiser` can forbid an edge that has never
been written, which is exactly what a layering contract is for. `ALL-ARCH0003` can only report an
edge that exists. A team that wants "the domain layer must never import the HTTP layer" gets it from
`dependency-cruiser` on day one and gets nothing from MCMR until someone writes the offending
import.

The two also differ in what a reader learns. Run on `personal/my/src`, `dependency-cruiser` reported
six violations against a three-rule contract in 0.46 s, every one naming the rule the project itself
wrote. On the same target `ALL-ARCH0003` reported nothing at all, and the seventeen findings
`ALL-ARCH0005` did produce are a derived zone-of-uselessness judgment the reader has to accept on
the tool's terms.

The honest conclusion is that these are complements, not competitors, and MCMR's design note reads
as if it settled a debate it only took one side of.

MCMR now has one policy system. Each rule owns its acceptance contract, and a project may override
that contract without selecting a built-in mode. A result outside the stated good and bad
sets stays `unassessed` rather than guessed. Clippy has group levels and ESLint has severities, but
neither models a measurement and its acceptance contract as separate values the way MCMR does.

## Fixes

| Tool | Fixes | Safety modelled |
| --- | --- | --- |
| Clippy | machine-applicable suggestions, `cargo clippy --fix`. 169 of the 218 pedantic and nursery warnings on the kernel are auto-applicable | yes, rustc's `Applicability` has four levels |
| rustc | many lints carry a structured suggestion | yes, the same four levels |
| ESLint | 106 fixable core rules plus 46 in typescript-eslint, 200 in unicorn | yes, `fixable` against `hasSuggestions` |
| oxlint | `--fix`, `--fix-suggestions`, `--fix-dangerously` | yes, three explicit tiers |
| Biome | `--write` and `--write --unsafe` | yes, safe against unsafe |
| **MCMR** | 23 fixes on 22 rules, and **no backend that applies any of them** | the model exists, `SAFE` against `REVIEW` |

MCMR's autofix design is thorough on paper. Six typed rewrite operations, conflict detection over
spans, import management, atomic application, reparse and re-run before an edit is kept, a bounded
fixpoint. `docs/autofix.md` describes all of it under the heading "What the backend owes a plan",
and there is no such backend. There is no `mcmr fix` command in the CLI, `RuleEngine.repaired`
attaches a plan to a finding and nothing writes a byte.

For these two languages the point is close to moot anyway. Of the 23 fixes, 18 are Python-scoped.
The five general ones are commented-out code, three inline-a-helper fixes, and a multiline string
literal that the design doc itself records as guarding on `subject.language` until a language backend
exists. On the Rust corpus exactly one fix-carrying rule fires, `ALL-COMM0002`, eight times. **On
TypeScript, zero fix-carrying rules can fire at all**, because `ALL-COMM0002` reads `CommentFact`
and the TypeScript frontend does not fill it.

Meanwhile `cargo clippy --fix` would rewrite 169 sites in the kernel today.

## Output quality

A finding has to tell a reader what to change and where. Measured by whether the reported span is a
real line or the file's first character.

| Report lines | at a real line | at line 1 column 1 |
| --- | --- | --- |
| MCMR on the kernel's Rust, 418 lines | 296 | 122 |
| MCMR on `personal/my/src`, 207 lines | 40 | 167 |

Seven of 22 failing rules localise on Rust. Two of 19 do on TypeScript. Every `RS-` and `TS-` rule
is in the non-localising set.

Side by side on the same concern.

```
clippy   src/graph.rs:317:13: warning: wildcard matches only a single variant and will also
                              match any future added variants: help: try: `Language::Python`
mcmr     graph.rs:1:1: RS-OWNE0002 Count the copies one module makes to avoid arranging a
                       borrow. (55, allowed <= 20)
```

Where MCMR does carry a finding it is often very good, and better than a linter message, because it
states the aggregate reasoning a per-occurrence rule cannot.

```
ALL-ARCH0004 `kernel::discovery` is imported by 10 modules and 0 of the 7 types it declares
state a contract, so every one of those importers is wired to an implementation
ALL-REAC0002 `dictionary.store.svelte.HistoryItem` is a public class read 2 times inside this
file and nowhere outside it
```

Those are actionable by a person and by an agent. The gap is that the rules producing them are the
general architectural ones, and the language-specific rules produce none.

Two smaller output defects found while measuring. `TS-TYPE0002` prints
`5.633802816901409`. And `ALL-HIST0002`, `ALL-ROUT0001`, and `ALL-ROUT0002` report at an empty path,
rendering as `:1:1`.

## Where the other tools are better than MCMR

Required section, and it is long.

**Clippy knows the types.** 482 default lints reason over a type-checked HIR. `unnecessary_cast`,
`redundant_closure`, `map_unwrap_or`, `needless_pass_by_value` all turn on knowing what a value is.
MCMR will never answer any of them. This is not a gap to close, it is the shape of the two tools.

**Clippy is already on.** Every Rust project that runs `cargo clippy` in CI gets 482 lints with zero
configuration, and 68 of them at `deny`. MCMR is an additional tool with an additional install and
its own rule contracts.

**Clippy fixes 169 things on MCMR's own kernel and MCMR fixes zero.**

**Clippy points at the token.** MCMR's Rust rules point at the file.

**Clippy is right and MCMR is wrong on the one lint they both claim about lifetimes.** 13 for 13.

**cargo-audit, cargo-deny, and cargo-geiger read evidence MCMR does not have.** The lockfile, the
advisory database, licence metadata, and the source of every transitive dependency. MCMR reads the
manifest and stops. Supply chain is a whole axis where MCMR contributes nothing.

**cargo-semver-checks answers a question MCMR does not attempt.** It compares two public APIs and
tells you whether the version number is a lie, while MCMR checks one current repository.

**Miri finds undefined behavior.** No static tool does, MCMR included.

**dylint and `clippy.toml` already give Rust projects their own rules, with more evidence.**

**tsc `strict` is worth more than every linter combined.** Eight flags, and the failure modes they
catch are the ones that produce real bugs.

**typescript-eslint's 61 type-aware rules are the highest-value TypeScript lints in existence**, and
all 61 are unreachable for MCMR.

**oxlint is six to eight times faster than MCMR and covers 844 rules.** 0.08 s against 0.63 s on the
same 111 files.

**Biome checks 352 files in 25 ms** and offers safe and unsafe fix tiers.

**knip understands the framework.** It reads `.svelte`, knows SvelteKit routes are entry points, and
reports unused files and dependencies alongside unused exports. MCMR's reach analysis produces
roughly 47 percent false positives on the same project purely because it never opens a component
file.

**type-coverage measures escape hatch density correctly** by asking the type checker, where
`TS-TYPE0002` is 86 percent wrong by grepping for the word `as`.

**Every tool measured here ran to completion on both corpora.** The Rust corpus holds 51 files with
a non-ASCII byte and the TypeScript corpus is a multilingual site full of Japanese, and Clippy,
oxlint, Biome, ESLint, tsc, and knip each read all of it without complaint. MCMR does not finish on
the Rust corpus at all.

**Every tool measured here excludes generated directories by default.** MCMR's exclusion set covers
`.git`, `.venv`, `node_modules`, `__pycache__`, `.chefe`, `target`, `build`, `dist`, `.pixi`,
`site-packages`, `.mypy_cache`, `.ruff_cache`, and `vendored`. It does not cover `.svelte-kit`,
`.next`, `.nuxt`, `.output`, `.wrangler`, `.turbo`, `coverage`, or `.astro`. On `personal/my`, **206
of MCMR's 348 reported lines are about generated SvelteKit files**.

**No tool measured here reported against a file that does not exist.** On a TypeScript project with no `pyproject.toml` anywhere, the
kernel emits a `ProjectConfigurationFact` with `key: "configuration:pyproject"`,
`language: "python"`, and `span.path: "pyproject.toml"`, and `PY-TYPE0003` reports a failure against
a file that does not exist. This is the exact class `tests/test_fact_variation.py` was built to
catch, and it slips through because MCMR's own repository does have a `pyproject.toml`.

## Where MCMR is better

Kept short because the losses above are the point of this document, but these are real.

**The repository is the unit.** `ALL-ARCH0003` through `ALL-ARCH0005` place every module against
Martin's main sequence and name the zone of pain without anyone writing a layering file. Nothing in
either ecosystem does this.

**Measurement separated from policy.** A count is a count and each rule owns the bar. Project
configuration can replace that rule's contract after validating the same output shape.

**One graph over a polyglot repository.** Python beside Rust beside TypeScript beside CUDA, with
cross-language seams found where one language declares a binary and another names it. A monorepo
running Clippy, ESLint, and Ruff gets three reports that never meet.

**History.** Churn, co-change, and hotspots, matched exactly against the Archy oracle. No linter
here reads git.

**`TS-TYPE0001`.** Twelve of thirteen against tsc's own answer on real source, no false positives
there, and 500 times faster. It is proof that a well-chosen syntactic proxy can stand in for a
type-checked answer, which is the argument the whole catalog rests on.

## Where MCMR should borrow next, ranked

`docs/backlog.md` items 23 through 26 cover floating promises, unnecessary conditions, needless pass
by value, and large enum variants. Every one of them is a good rule and every one is ranked far too
high, because all four sit behind evidence the frontends do not produce and two of them need type
inference MCMR does not have. Fixing what already claims to work should come first.

**1. Stop the kernel crashing on non-ASCII Rust.** `src/core/src/rust.rs` lines 112 and 138 slice on a
byte index. Four crates out of five in a normal corpus contain a character that kills the whole run.
Nothing else on this list matters until `mcmr check` finishes on real Rust.

**2. Fill `control_increments` in the Rust, TypeScript, and native frontends.** This is one field and
it unlocks `ALL-FUNC0008` and `ALL-FUNC0009`, restores the truth of the backlog's own cross-language
claim, makes the `cognitive_complexity` Clippy claim real, completes the `excessive_nesting` one, and
makes the ESLint `max-depth` claim real too. The Python frontend already computes nesting-annotated
increments, so the model is settled and only the walk is missing. Higher value per line of work than
anything below.

**3. Read `TS-TYPE0002`'s evidence from the AST instead of the text.** The oxc tree is in scope in
the same file. `TSAsExpression`, `TSNonNullExpression`, `TSAnyKeyword`, and a comment scan for
`@ts-ignore` give the exact answer, and drop the false positive rate from 86 percent to zero. Until
this lands the flagship TypeScript rule is actively misleading and I would rather see it disabled
than shipped.

**4. Look through `ExportNamedDeclaration` in `erasable()`.** Two lines, and `TS-TYPE0001` goes from
92 percent recall to complete. It is the highest-quality TypeScript rule MCMR has and this is the
only thing wrong with it.

**5. Fix `RS-LIFE0001` or withdraw it.** Filter on `annotation.kind` so type, alias, and trait
declarations are excluded as the docstring already promises, and restrict the "never reaches the
output" branch to lifetimes appearing in exactly one input position. Both are small. Thirteen for
thirteen wrong on MCMR's own source is worse than not shipping the rule.

**6. Give every `RS-` and `TS-` rule findings.** Nine rules, zero findings between them, and the
evidence they need is already in the fact. `LifetimeAnnotation` carries `owner` and `line`,
`erasable_violations` carries `kind`, `name`, and `line`, `escape_hatches` carries `kind` and
`line`. This is wrapping a value in `Reported` and nothing more, and it is the difference between a
report a person can act on and a number they have to reverse engineer.

**7. Extend the default exclusion set to the JavaScript ecosystem's generated directories.**
`.svelte-kit`, `.next`, `.nuxt`, `.output`, `.wrangler`, `.turbo`, `.astro`, `coverage`. Sixty
percent of MCMR's output on a real SvelteKit project is currently about files nobody wrote.

**8. Fill `SyntaxFact` from the TypeScript frontend. Landed.** This closed the largest coverage
item and made the three ESLint syntax claims executable.

**9. Fill `CallFact` and `CommentFact` from the TypeScript frontend.** Six more general rules, and
`CommentFact` is what makes `ALL-COMM0002` the first fix any TypeScript project could use.

**10. Read `.svelte`, `.vue`, and `.astro` for references.** Not full parsing, just enough to count
a symbol as reached. Forty-seven percent of the reach findings on a Svelte project are wrong today,
and a component-aware reference scan is what knip does and what makes its answer trustworthy.

**11. Freeze an ESLint and typescript-eslint inventory in `mcmr/data/`. Landed.** The suite
re-derives both inventories from their package registries, and the gap accounts cover every rule.

**12. Make the coverage account language-aware.** `ALL-CONT0002` states in its own docstring that it
cannot answer for Rust, and `mcmr coverage --tool clippy` records it as a native claim anyway.
`test_upstream_coverage.py` already requires a Python message to name a rule whose scope could
answer it. The same check for a Rust or TypeScript claim would have caught this and two others.

**13. Add a language corpus to `tests/test_fact_variation.py`.** The ledger is MCMR's best defence
against a fabricated field and it currently reads one language. Run over the Rust and TypeScript
corpora it immediately flags `control_increments` as frozen, along with all four `python_target`
fields of the invented `pyproject` configuration fact, and 130 and 114 other fields besides.
Everything above item 13 is a symptom of this one being missing.

Then, and only then, the backlog's own 23 through 26.

**Floating promise, item 23**, is the strongest of the four and I agree with its framing that it is
`ALL-CALL0001` with a configured contract rather than a new rule. It needs `CallFact` from the
TypeScript frontend, which is item 9 above, and it needs the call to be known to return a promise,
which without types means matching `async` declarations in the same project and nothing else.
Partial coverage, honestly scoped, is worth having.

**Needless pass by value, item 25**, and **large enum variant, item 26**, both need type layout
information. Clippy computes actual sizes through `rustc_target`. MCMR can at best match a syntactic
pattern such as an owned `String` or `Vec` parameter never moved in the body, which is a real subset
and should be described as one rather than as generalizing the Clippy lint.

**Unnecessary condition, item 24**, needs type narrowing and the backlog already says so. I would
move it out of the ranked list entirely and into the ownership boundary table as something
typescript-eslint owns, because "needs the optional semantic stage" has been true since the item was
written and the stage does not exist.

One disagreement with the boundary table itself. It says Clippy owns "Rust local correctness and
idiom" and MCMR mirrors "only the design-level lints as general rules". Of the ten Clippy lints the
catalog claims, `no_effect`, `dbg_macro`, `print_stdout`, and `let_underscore_must_use` are local
correctness and idiom by any reading. The table describes a boundary the catalog does not hold. I
would either widen the table's wording or drop the four claims, and I prefer dropping them, because
Clippy reports all four by default with a span and a suggestion and MCMR reports two of them and
localises neither.

## Errors found in MCMR's own documentation

Reported rather than fixed, per the terms of this exercise.

`docs/backlog.md` states that cognitive complexity "is the proof that one rule can answer for every
language". It answers for Python only. No frontend but the Python one fills `control_increments`.

`docs/kernel.md`, in the section "What Rust rules judge", states "Zero `'static` demands and zero
elidable annotations remain" for the kernel. Today `RS-LIFE0001` reports 13 and `RS-LIFE0002`
reports 3 on the same source. The kernel has grown by a whole TypeScript frontend since that
sentence, so this is drift rather than an error at the time, but the sentence reads as a current
claim.

The stale TypeScript `SyntaxFact` gap was removed from `tests/test_language_coverage.py`. Its
remaining TypeScript gap is `CommentFact`, which is explicit and fails in both directions.

`src/rules/mcmr/rules/rust/deterministic/lifetimes/r0001.py` documents an exception its implementation does
not honour, "A trait or type that names a lifetime is not judged here at all", and `is_elidable`
never reads `annotation.kind`.

`src/rules/mcmr/rules/typescript/deterministic/types/r0002.py` documents "Each finding names the module,
its measured lines, and every hatch with its kind and line", and returns a bare `Percentage` with no
findings. The same mismatch between a documented `Evidence` section and a bare value appears in all
five `RS-` rules and all four `TS-` rules.

## Every command in this document

```sh
# rule inventories
clippy-driver -W help - < /dev/null
node -e "const {builtinRules}=require('eslint/use-at-your-own-risk');console.log(builtinRules.size)"
node -e "const p=require('@typescript-eslint/eslint-plugin');/* count meta.docs.requiresTypeChecking */"
oxlint -D all -D nursery --import-plugin --react-plugin --print-config
node -e "require('@biomejs/biome/configuration_schema.json')"
tsc --all

# MCMR against each corpus, run through the chefe environment as `python -m mcmr.cli`
mcmr check src/core/src --suffixes .rs --format concise --limit 400
mcmr check /path/to/rust-corpus --suffixes .rs --format concise
mcmr check /path/to/project/src --suffixes .ts --format concise --limit 500
mcmr check src/core/src --suffixes .rs --select rust.deterministic.lifetimes
mcmr coverage --tool clippy

# the fact families and fields each frontend actually fills, over one corpus
echo '{"families":["FunctionFact"],"suffixes":[".rs"],"root":"/path"}' | mcmr-kernel

# oracles
tsc --noEmit --erasableSyntaxOnly -p tsconfig.json
type-coverage --detail -p tsconfig.json
cargo clippy --offline -- -W clippy::pedantic -W clippy::nursery

# the field
oxlint --no-ignore src
biome lint src
eslint -c eslint.config.mjs src        # with tseslint.configs.recommendedTypeChecked
knip --no-config-hints
ts-prune -p tsconfig.json
depcruise --config .dependency-cruiser.cjs src
madge --extensions ts,svelte --circular --ts-config tsconfig.json src
cargo-audit audit
cargo-geiger
cargo-machete
```
