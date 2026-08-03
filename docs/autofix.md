# Autofix design

A rule reports a measurement. A fix states how to repair what that measurement found. This page
freezes how a fix is written, what the language backend owes it, and which rules can carry one.

## What a fix is

A fix is a typed rewrite program over nodes the provider already resolved. It is not a text patch
the rule computes and not a name the provider looks up. The rule names which nodes change and how,
and the backend renders the change against the parsed tree.

The program is relational. A rule that can repair a finding declares `fix_safety` on `@rule` and
returns one lazy `FixQuery` beside its value and finding queries. The query carries normalized
rewrite, node, and requested-import rows keyed by the same `fact_id` as the finding. A row that does
not qualify produces no rewrite rows. The collector materializes these relations only for bounded
failures, then builds the typed rewrite operations the renderer consumes.

Safety is stated only by the decorator. `FixQuery` carries no second safety value that could
disagree. Node and import relations default to typed empty relations, so a rewrite that needs
neither does not construct empty frames by hand.

This keeps execution table-only. The engine does not invoke a second fix callable for each fact,
reconstruct a Pydantic fact, or ask a provider for a candidate edit. A rule selects the finding and
its repair inputs in the same Polars plan, while the provider supplies only resolved nodes and
primitive source coordinates.

The retired contract asked the provider to precompute candidate edits and let a row-level fix
retrieve one by name. That put the whole rewrite inside an unnamed provider contract. A new fix
needed provider changes and every fact carried candidate edits for rules that never fired. The
relational contract removes that provider verdict and keeps the rule responsible for its rewrite.

## The rewrite algebra

Seven operations, each earned by a fix that already exists.

| Operation | Meaning | Used by |
| --- | --- | --- |
| `Remove(target)` | delete a node with the separators and trivia that only exist to hold it | unused import, `__future__` import, redundant `scalars`, commented-out code, unreferenced private function |
| `RemoveDirectory(target)` | remove one exact existing empty physical directory | empty source directory |
| `Replace(target, source, imports)` | replace a node and declare each binding the new source needs | tuple display, model constructor, fluent tensor chain, relative import, logger boundary |
| `Move(target, anchor, placement, prefix, imports)` | relocate an existing node, optionally across existing files, and satisfy destination imports | literal setup lifted above a `try`, helper moved into its sole owning class, initializer declaration placed beside its constructed owner |
| `Unwrap(target, keep)` | replace a node with a descendant it already contains | redundant `bool` conversion |
| `Rename(symbol, name)` | rename a declaration and every reference bound to it | Boolean predicate naming |
| `Inline(declaration, body, references)` | replace every reference with the body, then remove the declaration | trivial helper, transparent wrapper, one-line nested function |

`Inline` was earned rather than designed. Three fixes had written out the same `Replace` at every
reference followed by a `Remove` of the declaration, in the same order, for the same reason. That
repetition is what a refactoring looks like before it has a name, and naming it lets the backend
keep the body and the sites consistent: it parses the body once, adapts it at each site, and either
every site and the declaration change together or none of them do.

There was another operation that never earned its place. `Insert` existed because an algebra that
can delete and replace looks incomplete without it, and no fix ever reached for it. MCMR found it
in its own source, as a public declaration nothing reaches, once type references became edges. An
operation earns its place by being used, and it leaves when it stops being.

Every materialized operation exposes `spans`, so the engine detects overlapping fixes generically
without understanding any particular rule. `FixPlan.rewrites` is non-empty by construction. A
finding with no collected rewrite rows has no plan, which keeps "nothing to do" and "an empty edit"
distinct.

Structural operations are language-neutral. `Replace` authors text and therefore belongs to a
language-scoped rule, or to a general rule that filters the table's `language` column until a
language backend can render the construct itself. `use_multiline_literal` follows that rule and
offers its relational replacement only for Python rows.

## What the Python renderer guarantees

The renderer supports all seven operations for `.py` and `.pyi` files. It turns provider spans into
half-open UTF-8 byte edits and proves each retained node still matches the current source. It keeps
line endings and indentation, consumes trivia owned by a deleted statement, rejects overlapping
edits, removes exact sequence items with their adjacent comma, and parses the complete revised file
before returning a diff. A non-Python plan is refused with a reason instead of being treated as a
text patch.

Each `Replace` or cross-file `Move` declares typed `ImportRequest` values for names its destination
needs. Those requests retain relative levels and type-only placement and are valid Python by
construction. The import manager recognizes an exact existing import, inserts missing runtime
imports after a shebang, encoding declaration, module docstring, and opening import block, inserts
type-only imports inside `TYPE_CHECKING`, and refuses to shadow a binding already held by the
module.

Application uses a sibling temporary file, flushes it to storage, preserves permissions, and
replaces the destination atomically. A plan spanning several files applies each file atomically and
rolls earlier files back if a later write fails. Empty-directory actions use guarded `rmdir`
semantics, refuse missing, symbolic, or newly nonempty targets, and recreate removed directories
during rollback. There is no filesystem primitive that can replace several paths as one
transaction, so rollback is the cross-path guarantee.

`FixSession` applies one `SAFE` plan at a time. It reruns the originating rule on the revised tree
and keeps the edit only when parse failures do not increase and the exact originating finding
message occurs fewer times. It then reruns the selected catalog before offering the next plan. A
failed verification is restored atomically and recorded as a refusal. The session stops at a
fixpoint or at `--maximum-fixes`.

`REVIEW` plans are never written unattended. They remain available as unified diffs because
inlining, renaming, and changes such as removing future annotations can alter behavior a reader has
to approve.

## Command line use

```sh
mcmr check .
mcmr check . --repair preview
mcmr check . --repair apply
mcmr check . --repair apply --maximum-fixes 20
mcmr check . --format full
mcmr check . --format concise
```

The default `rich` view shows a compact analysis and timing table, one navigable panel per precise
diagnostic, source context where the location is a file, model provenance, measurements, evidence,
and repair safety. Loading states cover repository analysis and fix verification in an interactive
terminal. The plain `full` and `concise` formats remain available for logs and parsers.

## Which rules can carry a fix

Thirty-one rules carry one fix each across five levels of rewrite capability.

* **L1 span deletion or local replacement.** Mechanical when marked safe. Unused import, empty
  directory, redundant `bool`, redundant `scalars`, enum `auto()`, and deprecated `asyncio` check.
  Exact grouped import bindings and explicit export items carry their own sequence nodes, so the
  renderer never has to reconstruct a list. Removing a `__future__` annotations import or an
  explicit export is review-only because runtime annotation representation and public routes can
  change.
* **L2 structural rewrite.** Safe once the parts resolve. Set comprehension, literal setup moved
  out of a `try`, SQLModel `exec`, model constructor, fluent tensor chain, relative import, logger
  boundary, deep import routed through an existing cycle-safe public facade, and one guarded return
  expressed through `contextlib.suppress`.
* **L3 project-wide symbol edits.** Needs a complete reference index, and the fix relation must
  filter `references_complete` before planning. Boolean predicate rename.

  This one had been unable to fire at all because the provider emitted no symbol-reference rows,
  so the completeness flag was always false and the fix declined every time. The kernel now
  addresses each module-scope declaration together with every load of it in the same file, and
  claims completeness only where
  that file is genuinely the whole world for the name. Two things break that and both are checked:
  a name reached by string through `getattr` or the module dictionary leaves no reference to find,
  and an `__all__` re-export hands the name to callers the file never sees. So `_ready` becomes
  `_is_ready` across its declaration and both uses, and an exported `ready` is left alone with a
  reason rather than with a silence. Renaming a public name still needs an index the whole
  repository shares, which the graph could supply once its edges carry spans rather than lines.

  The rename also used to drop the leading underscores while inserting the prefix, which would have
  published a private name. They are how the language states visibility, so they are carried over.
* **L4 review-only suggestions.** Correct as a proposal, not as an automatic edit. Inline a trivial
  helper, inline a transparent wrapper, inline a one-line nested function, move a helper into the
  only class method that calls it, move an initializer function beside the only exact sibling class
  it constructs, tuple to list display, delete commented-out code, delete an unreferenced private
  function, remove an explicit `__all__` declaration outside an initializer, and remove an unused
  explicit export.
* **L5 no fix.** Most of the catalog. A measurement rule such as module line count, and every rule
  whose repair requires a design decision, has no defensible mechanical rewrite.

Four of those are new, and each one came with the evidence it needed rather than with a guess.
Deleting commented-out code needed the comment group to carry a node, so the kernel now gives it
one, and doing that exposed a real extractor bug: the group body was trimmed of its indentation
before being parsed, so no commented block with any structure ever parsed as source and the rule
had been quietly finding almost nothing. Routing a call through the project logger needed the
callee addressed separately from the whole call, which the kernel already recorded. Deleting an
unreferenced private function needed nothing new, because the rule already proves what the fix
depends on: the declaration is nonpublic, undecorated, and reached only by itself.

The line every one of these holds is that a fix plans only where its rule fired. The same predicate
selects the finding and the rewrite rows, so no second invocation can disagree with the rule that
reported it.
