# Autofix design

A rule reports a measurement. A fix states how to repair what that measurement found. This page
freezes how a fix is written, what the language backend owes it, and which rules can carry one.

## What a fix is

A fix is a typed rewrite program over nodes the provider already resolved. It is not a text patch
the rule computes and not a name the provider looks up. The rule names which nodes change and how,
and the backend renders the change against the parsed tree.

A fix returns the rewrites it wants and nothing else. Whether those rewrites amount to a plan is
not its decision, so a fix that finds nothing to change returns no rewrites and the framework turns
that into the absence of a plan. Its own first line of documentation is the summary, because the
sentence describing what a fix does and the sentence shown beside its diff are the same sentence.
That leaves nothing for a helper to do.

```python
@unused_import.fix(is_default=True)
def remove_unused_import(subject: ImportBindingFact) -> list[SourceRewrite]:
    """Remove the declaration of an import proven unused."""
    return [Remove(target=subject.declaration)] if subject.declaration else []
```

The earlier contract asked the provider to precompute candidate edits and let the fix retrieve one
by name. That put the whole rewrite inside an unnamed provider contract: the fix could not be
tested without a provider, a new fix needed provider changes, and every fact carried candidate
edits for rules that never fired. Fixes now own their rewrites and are testable as ordinary
functions.

## The rewrite algebra

Six operations, each earned by a fix that already exists.

| Operation | Meaning | Used by |
| --- | --- | --- |
| `Remove(target)` | delete a node with the separators and trivia that only exist to hold it | unused import, `__future__` import, redundant `scalars`, commented-out code, unreferenced private function |
| `Replace(target, source)` | replace a node with source the backend parses first | tuple display, model constructor, fluent tensor chain, relative import, logger boundary |
| `Move(target, anchor, placement)` | relocate an existing node without rewriting it | literal setup lifted above a `try` |
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

Every operation exposes `spans`, so the engine detects overlapping fixes generically without
understanding any particular rule. `FixPlan.rewrites` is non-empty by construction: a fix that does
not apply returns no plan at all, which keeps "nothing to do" and "an empty edit" distinct.

Structural operations are language-neutral. `Replace` authors text and therefore belongs to a
language-scoped rule, or to a general rule that guards on `subject.language` until a language
backend can render the construct itself. `use_multiline_literal` is the one general rule that
guards today, and it is the first candidate for a renderer.

## What the backend owes a plan

* **Rendering.** Turn each operation into byte edits, including the trivia rules a text patch gets
  wrong: a removed import leaves no blank line, a moved statement keeps its indentation, an
  unwrapped expression keeps the parentheses it still needs.
* **Import management.** A `Replace` that names a symbol the file does not import is completed by
  the backend, the way Ruff's importer does. No fix inserts an import itself.
* **Conflicts.** Two plans whose spans overlap never merge. The engine applies the higher priority
  plan, then re-runs analysis; the other plan is offered on the next pass if it still applies.
* **Verification.** Apply atomically per file, reparse, and keep the edits only when the file still
  parses and the rule that produced the plan no longer reports the finding. A plan that fails
  either gate is reverted and reported, never written.
* **Iteration.** Repeat to a fixpoint under a bounded iteration count, since one fix can expose
  another.
* **Safety.** `--fix` applies `SAFE` plans only. `REVIEW` plans are rendered as a diff for a human,
  because inlining a helper or renaming a symbol changes meaning a reader has to agree with.

## Which rules can carry a fix

Twenty-three fixes exist across five levels of rewrite capability.

* **L1 span deletion or local replacement.** Fully mechanical, safe. Unused import, `__future__`
  import, redundant `bool`, redundant `scalars`, enum `auto()`, deprecated `asyncio` check.
* **L2 structural rewrite.** Safe once the parts resolve. Set comprehension, literal setup moved
  out of a `try`, SQLModel `exec`, model constructor, fluent tensor chain, relative import, logger
  boundary.
* **L3 project-wide symbol edits.** Needs a complete reference index, and the fix must check
  `are_references_complete` before planning. Boolean predicate rename.

  This one had been unable to fire at all: nothing filled `SymbolRef`, so the completeness flag was
  always false and the fix declined every time. The kernel now addresses each module-scope
  declaration together with every load of it in the same file, and claims completeness only where
  that file is genuinely the whole world for the name. Two things break that and both are checked:
  a name reached by string through `getattr` or the module dictionary leaves no reference to find,
  and an `__all__` re-export hands the name to callers the file never sees. So `_ready` becomes
  `_is_ready` across its declaration and both uses, and an exported `ready` is left alone with a
  reason rather than with a silence. Renaming a public name still needs an index the whole
  repository shares, which the graph could supply once its edges carry spans rather than lines.

  The rename also used to drop the leading underscores while inserting the prefix, which would have
  published a private name. They are how the language states visibility, so they are carried over.
* **L4 review-only suggestions.** Correct as a proposal, not as an automatic edit. Inline a trivial
  helper, inline a transparent wrapper, inline a one-line nested function, tuple to list display,
  delete commented-out code, delete an unreferenced private function.
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

The line every one of these holds is that a fix plans only where its rule fired. A fix does not
re-derive the rule's conditions, and it must not be called on a fact the rule passed, which is why
the engine and not the fix decides when to ask.
