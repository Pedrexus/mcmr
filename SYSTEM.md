# MCMR system

My Code, My Rules defines engineering policy as typed Python callables. Phase one freezes the
authoring surface before selecting parser, graph, model, or Rust implementations.

## Rule contract

Each rule lives in one file under `rules/{lane}/{family}/rNNNN.py`. Its identifier is derived from
that path. For example, `rules/deterministic/imports/r0003.py` becomes `PY-IMPO0003`. Catalog
construction fails on invalid paths, duplicate identifiers, ambiguous parameters, incomplete
documentation, incompatible fixes, or multiple default fixes.

The first parameter is the smallest independently invalidated fact consumed by the rule. Further
required parameters may later request explicit indexes or services. Keyword-only defaults are
developer settings. The return annotation defines a Boolean, count, percentage, or closed category
result.

Only an algorithm knob belongs in a rule signature. Repository selection belongs to a provider,
model identity belongs to an injected backend, and pass or fail thresholds belong to policy. A
rule parameter that does not affect its implementation is rejected by the catalog tests.

Rules may be synchronous or asynchronous without changing their declaration shape.

```python
@rule
def unused_import(subject: ImportBindingFact) -> Occurrence:
    """Report an unused import binding.

    Definition
    ----------
    Report one resolved import binding without a qualifying use.

    Evidence
    --------
    Retain the binding and its resolved reference summary.

    Exceptions
    ----------
    Keep explicit re-exports and documented side-effect imports.

    Examples
    --------
    ``import json`` without a reference fails.

    References
    ----------
    Generalizes Pylint W0611 unused-import
    Generalizes Ruff F401 unused-import
    """
    return (
        subject.reference_count == 0
        and not subject.has_qualifying_use
        and not subject.is_reexported
        and not subject.is_type_only
        and not subject.has_documented_side_effect
    )
```

The full reStructuredText docstring is the source for future rule pages. Every rule keeps a clear
definition, evidence contract, exceptions, examples, and references.

## Docstring template

A rule page is generated rather than written, so the docstring is a format rather than a habit. One
expression reads a whole one, and `tests/test_rule_template.py` holds every rule to it.

```
    """{summary}

    Definition
    ----------
    {prose}

    Evidence
    --------
    {prose}

    Exceptions
    ----------
    {prose}

    Examples
    --------
    {prose}

    References
    ----------
    {reference lines}
    """
```

The summary opens on the same line as the quotes, ends like a sentence, and fits the one line a
website card gives it. The five sections always appear, always in that order, each underlined by as
many hyphens as its own heading has letters, and separated by one blank line. Examples may open
sub-rubrics such as `Bad` and `Good` underlined with `~`. The closing quotes stand on their own
line, which is not a style preference: a References section ends in a quoted work title, and a line
ending in `"` written against `"""` is not valid Python.

## Reference grammar

References carry the provenance, and the section holds references and nothing else. One regular
expression reads every line of it, `ReferenceParser.grammar` is that expression rather than a
description of one, and a line it does not match fails the catalog rather than becoming prose.

```
(?P<url>https?://\S+)
|(?P<relation>Generalizes|Adapts|Cites) (?:"(?P<work>[^"]+)"(?:, (?P<locator>.+))?
|(?P<tool>[A-Za-z][A-Za-z0-9-]*)(?P<identity>(?: [A-Za-z0-9][\w.-]*){1,2}))
```

A line naming one rule of one upstream tool reads `relation tool identity [identity]`, where the
relation is `Generalizes` when MCMR answers what that rule answers, `Adapts` when it asks a
different question about the same concern, and `Cites` when it names prior art and claims nothing.
A line naming one published work reads `relation "Title"` with an optional locator behind a comma,
where the locator is the chapter or section the rule leaned on. A bare URL line attaches to the
entry above it and a URL with nothing above it is refused.

```
Generalizes Pylint R0904 too-many-public-methods
Adapts Ruff PLR0904 too-many-public-methods
Cites "A Philosophy of Software Design", chapter 4, deep and shallow modules
Cites "Refactoring", Replace Conditional with Polymorphism
https://refactoring.com/catalog/replaceConditionalWithPolymorphism.html
```

The quotes are what make a work syntactically distinct from a tool, which is the same job the
relation word does for the tool half. Both halves are positional and neither infers anything from
the shape of the words. A work is therefore one identity however many rules cite it, enforced by
the syntax rather than by a table of spellings, which is what an alias map could never be: the
literature half was free prose for exactly as long as it took one book to arrive as
`Fluent Python`, as `Luciano Ramalho, Fluent Python`, and as `Fluent Python, chapter 5`. An author
never appears in a reference line, because the work is the identity and the person is display
detail.

`src/mcmr/data/works.json` registers every citable work with its canonical title, its kind, its
author, and its link, which is what a generated page needs to render a citation. Registration does
no resolution, since the quoted title is already the key. A title nothing registers fails the parse
and a registered work nothing cites fails the guard, so the registry can neither invent a row nor
keep a dead one.

`mcmr coverage` derives the account of any tool from those statements and `InfluenceReport` derives
the whole influence table, tools and literature alike, from the same lines. No table beside the
catalog can disagree with what a rule says about itself.

Each inventoried tool also declares the languages it reads. A language-specific rule covers only
a tool with that exact language boundary. A general rule can cover every language in the tool's
boundary only when the language coverage ledger proves that its fact family has a provider there.
This keeps a true comparison in Python from silently becoming a false coverage claim for C++ or
TypeScript.

## Autofix contract

A rule may expose no fixes or several typed fixes. Fix signatures must match their rule inputs and
settings. A sole fix becomes the default automatically. Several fixes require at most one explicit
default. Review fixes are never treated as safe edits.

A fix returns the rewrites it wants over nodes the provider resolved, not a text patch and not the
name of a provider-computed candidate. `Remove`, `Replace`, `Move`, `Unwrap`, and `Rename` are the
five operations, each exposing the spans it touches so the engine detects conflicts without knowing
any rule. Whether those rewrites amount to a plan is the framework's decision, so a fix that finds
nothing to change returns no rewrites, and its own first line of documentation is the summary.

```python
@unused_import.fix(is_default=True)
def remove_unused_import(subject: ImportBindingFact) -> list[SourceRewrite]:
    """Remove the declaration of an import proven unused."""
    return [Remove(target=subject.declaration)] if subject.declaration else []
```

The backend renders each operation against the parsed tree, manages imports a replacement needs,
applies a plan atomically, reparses, and keeps the result only when the file still parses and the
rule no longer reports the finding. `docs/autofix.md` holds the full contract and the fix inventory.

## Fact injection

Rules name the exact fact stream they consume. The planner groups them by first parameter type, so
providers parse or resolve each stream once and fan it out to every dependent rule. A local rule
does not receive a whole repository when it only needs one import binding, function, query, or prose
segment.

Providers populate primitive evidence such as resolved calls, symbol uses, source spans, graph edges,
line counts, and checklist observations. A fact must not expose a field named after any rule, and no rule may
return one Boolean field as its whole answer. Either shape would let a provider or model backend
decide the finding and hand it back through the fact. The catalog tests reject both.

Facts carry resolved structure, and rules carry vocabulary. A call site carries its resolved
arguments as an expression tree, not a normalized pattern string, so the set of interesting names
lives in the rule module that owns it. This is what lets one rule about fluent tensor chains cover
a family of nested calls instead of one exact expression.

All facts and callable wrappers use frozen Pydantic models. Collection defaults use concise `[]`
and `{}` declarations. Pydantic copies them for every model instance, which the tests verify. The
frozen contract prevents field reassignment but does not pretend that nested lists and mappings are
deeply immutable.

`FrozenRootModel` provides the common contract for one-value evidence objects. Concrete models own
a typed `root` field. This avoids the untyped surface inherited from Pydantic `RootModel` under the
strict Mypy configuration while retaining validation, serialization, and frozen behavior.

Evidence objects may provide small fluent queries when several rules share a derived measurement.
`Checklist.coverage()` and `LengthDistribution.at_least().uniformity()` keep those calculations
near their data. `CallFact.call_counts` builds its reusable index lazily with `cached_property`, so
providers still supply only primitive call sites and repeated rules do not rebuild the index.

For example, `ALL-ARCH0011` receives one `DependencyComponentFact` holding every import the
repository graph resolved between two modules this repository owns, each edge naming both ends by
the qualified module name the graph gives them and carrying the file and line that state it. The
rule computes strongly connected components and returns the number of cyclic ones. It never
receives an `import_cycles` number. Likewise, call rules receive resolved call sites and calculate
their own counts.

A fact has to be able to hold the answer, and that half is easy to get wrong in a way no test
notices. This family used to be built one file at a time, carrying that file's external imports
with the source spelled as a path and the target spelled as an import line, so the two ends of
every edge came from different vocabularies, no component could form, and the rule reported a clean
repository for every repository there is. The scope was the first mistake and the vocabulary was
the second, because a file cannot see what imports it, so no per-file builder could have answered
this whatever it spelled. The family is derived from the graph after extraction now, alongside
`ModuleCouplingFact`, `OverrideFact`, and `SymbolReachFact`, which are repository-wide for the same
reason. `tests/test_fact_scope.py` holds both halves of that lesson: a `Relation` has to show its
two columns meeting somewhere in the corpus, and a rule declaring a floor on distinct files has to
read a family the corpus shows holding that many.

## Semantic cases

Catalog invocation and semantic correctness are different tests. The generic catalog test proves
only that discovery, dependency injection, settings, result validation, and fixes can invoke every
contract. It does not claim that a rule is correct.

Every deterministic rule is therefore imported directly by a focused test and called inside an
assertion. The test suite rejects a deterministic module without such an assertion. Cases use
concrete primitive facts and exact expected values. They cover these boundaries when applicable.

* Occurrence rules cover a matching case and a documented exception.
* Count rules cover zero, one, and several qualifying records.
* Percentage rules cover an empty denominator, partial coverage, and full coverage.
* Category rules cover every reachable category, including not applicable or uncertain states.
* Graph rules cover acyclic input, self cycles, multi-node cycles, and disconnected components.

Several assertions may share one fact containing qualifying and nonqualifying records. This checks
that the rule selects evidence correctly rather than merely recognizing an isolated positive.

## Migrated catalog

The catalog contains 218 declarations across 55 families. It preserves all 205 migrated GE4M rule
identifiers and their documented intent while removing settings that never affected an
implementation. The lanes hold 155 deterministic rules, 3 GLiNER rules, and 60 LLM rules. Nineteen
fixes are attached to rules with a defensible rewrite.

Scope names the language a rule answers for. `general` answers for every language, and `python`,
`rust`, `typescript`, `cpp`, and `cuda` answer for one, carrying the exact name a provider labels
its facts with. Identifier prefixes follow that scope: `ALL`, `PY`, `RS`, `TS`, `CPP`, `CU`. A rule
whose language no fact carries is skipped and counted, never refused, so a repository holding one
language does not have to deselect the rules of another.

Three class and encapsulation rules moved from the Python scope to the general scope once shared
`Visibility`, `MemberKind`, and `ReceiverKind` vocabulary existed. `docs/generalization.md` records
the mapping between that vocabulary and each language, `docs/backlog.md` records what to build next
and who already owns what, and `docs/autofix.md` records the fix contract.

Closed model categories are `StrEnum` classes. The enum supplies runtime validation, prompt labels,
and generated documentation without repeating a literal return type and a separate tuple. A
Boolean occurrence reports whether its exact fact is a match. A count reports a real aggregate.
Direct `int(predicate)` returns are rejected because they hide occurrence semantics inside a count.

Numeric fact fields state their own domain through `NonNegativeInt`, `PositiveInt`, and
`NonNegativeFloat` rather than repeating a `Field` constraint, and a `Ratio` alias carries the
values bounded to zero and one.

The deterministic lane now calculates its outputs from primitive facts. The model lanes remain an
explicit design boundary. Their invocation tests prove the typed backend contract only. They do not
yet prove stable semantics across models. Each model rule still needs a cited criterion schema,
good, bad, boundary, uncertain, and conflicting evidence cases, plus a deterministic reducer. A
model should estimate only the contextual criteria that cannot be extracted reliably. It should not
choose the final policy result when a deterministic decision table can do so.

## Policy

A rule reports an observation and a project decides what that observation is worth. That split is
what keeps a measurement honest: module length, complexity, and nesting depth are facts about a
codebase, and summing them or comparing them to a number this project never chose would be an
opinion wearing a measurement's clothes.

Three typed policies decide an observation. `Numeric` requires a value inside a closed interval,
`Boolean` requires one exact value, and `Category` accepts a named set. Every observation comes back
`pass`, `fail`, or `unassessed`, and a rule with no policy stays unassessed rather than guessed.
`mcmr check` exits nonzero only on a failure.

A profile is one named strictness level. `relaxed` judges only occurrences, since an occurrence rule
names a specific defect and its absence is not a matter of taste. `standard` adds the shape most
projects want, where a count is a count of findings unless the rule measures something and the
measuring rules carry explicit intervals. `strict` keeps that shape and tightens every magnitude.
Some rules are deliberately opinionated, and the profile is where a project says how much of that
opinion it wants.

## Findings

A rule answers with a number. A report has to answer with a place, a sentence, and something to do
about it. Every rule already documents an `Evidence` section stating exactly what its finding
records, and the engine used to narrow all of it to one scalar, so `ALL-CLAS0002 classes:facts.py 3`
named neither the three classes nor the members nor the lines.

`Finding` carries the second answer: a message about that finding, the `SourceSpan` every fact
already provides, named `Measurement` numbers, and one `Repair`. A repair is an `Edit` carrying a
`FixPlan` the backend renders, or a `Choice` naming a decision somebody has to make. Those are two
types rather than one optional patch, because offering a judgment as though it were an edit is how
a tool teaches people to distrust it.

The seam is `Reported[Value]`, the value beside its findings. A rule opts in by changing its return
annotation from `Count` to `CountReport`, from `Occurrence` to `OccurrenceReport`, from `Percentage`
to `PercentageReport`, or from a category to `Reported[TheCategory]`. `output_contract` looks
through it to the value type, so the unit, the category set, and the contract fingerprint a run
record keeps are all unchanged, which is what lets two runs taken either side of a migration still
compare. The engine reads both shapes through `answered` and `explained`, so a rule that has not
migrated is not special-cased anywhere, it simply states no findings. `Answer` is a protocol rather
than the model itself in the outcome union, because pydantic generics are invariant and a rule
states its exact value type.

A rule that already declares a default fix states no repair of its own. The engine asks that fix for
the rewrites it wants over the same fact and attaches the plan to every finding that proposed
nothing, so `PY-IMPO0003` reports a real removal without restating the edit its fix already makes.

`mcmr check` prints one output in two registers, both text, because a structured side channel is a
second thing to keep honest. The concise register is the line ruff writes, `path:line:column: CODE
[*] message`, which a person greps and a program splits on its first colons. The full register
quotes the source under an arrow with the span marked and a `help` line naming the repair. `[*]`
marks a finding an edit closes and never a choice. A rule that has not migrated still reaches the
page through its summary and the span of the fact it read, so the remaining gap is visible rather
than hidden. `tests/test_rule_findings.py` holds the ledger of which rules have migrated, fails in
both directions, and holds a second guard that the migrated slice still covers every result shape.

Migrating one more rule is mechanical. Change the return annotation to the reporting alias. Build
the list of records that fired instead of folding them into `sum` or `any`, and compute the same
value from that list, so the verdict cannot move. Return `Reported(value=..., findings=...)`. Write
a message about that finding rather than about the rule, naming the specific thing, the number that
triggered it, and what to change, with `counted` for any quantity that can be one. Locate it as
precisely as the fact allows, which is a record's own `NodeRef` or `SourceSpan` where it has one,
`SourceSpan(path=...)` where it has only a path, and `item.span or subject.span` where a frontend
may not have filled one. Name measurements with spaces rather than underscores so the docstring can
quote them without tripping the setting-name guard. Attach a `Choice` where the repair is a
judgment and nothing at all where the rule already declares a default fix. Rewrite the `Evidence`
section to say what the finding now records, leaving `References` alone. Change every test assertion
from `rule(fact) == 3` to `rule(fact).value == 3`. Then add the rule to the ledger with the shape it
proves and assert its message, its location, and its measurements against the fixture project.

Carrying evidence is not free and the cost sits in one place. A rule whose findings are the records
that fired pays only for what fired, so `ALL-CLAS0002` builds 35 findings over 411 facts in 0.8 ms.
A pure measure is the expensive case, because the measurement is the answer and the finding exists
even where the value passes, so `ALL-FUNC0001` costs 3.65 ms over 650 facts against 0.02 ms for
reading the field alone. Rendering reads back only the files a shown finding points into, which is
0.7 ms for a bounded view and 15.9 ms for every failure this repository has.

## Recorded runs

`mcmr check` judges a repository as it stands and keeps nothing, which answers what the code is and
never whether it is getting better. `mcmr snapshot` records the same judgment as one readable JSON
file per run under `.mcmr/runs`, beside the evidence a project already states about itself there.

A record holds the commit, the branch, whether the tree was clean, the profile, and for every
selected rule the bar that profile applied, how many observations it made, how many nothing could
judge, and every site it failed at beside the value it read. The value matters as much as the site:
a rule failing once at three and later once at seven has not stayed still.

Two runs are only comparable where they were judged the same way, and `mcmr diff` states that
rather than assuming it. A different profile is refused outright, since two verdicts stating
different intentions have no difference worth reporting. A rule the baseline never held, a rule the
catalog has since dropped, and a rule whose contract or whose bar moved are each named in a list of
their own and left out of every count a reader reads as a direction, so a rule added after a
baseline was taken can never be reported as a regression. What is left is a real comparison, where
a site can appear, be resolved, grow further outside the bar, or ease back toward it, and the sum
of those four is the one number the report orders by. `mcmr trend` draws the same comparison across
a whole series and prints the catalog fingerprint beside each run, so a jump in the totals is
attributable rather than mysterious.

Every fingerprint is derived rather than stored twice. A rule's contract fingerprint covers the
fact family it reads, its result shape, its unit, its categories, and its default settings, and
deliberately not its documentation, so rewording a docstring leaves two runs comparable. The
judgment fingerprint adds the bar as its shape and its rendered allowance rather than as its own
serialization, because a set of accepted categories iterates in whatever order the process hashed
it and a fingerprint that moved between processes would report a rule as redefined every other run.

## Analysis kernel

Discovery, parsing, and fact extraction live in a Rust crate under `kernel/`. It answers one
request and exits, and the request names only the fact families the selected rules read. Rules
declare their fact type as their first parameter, so the planner derives that set from the
signatures, asks for exactly those families, and hands each stream to the rules that named it. A
family nobody selected is never built, never parsed for, and never serialized.

The response is one JSON document whose field names match the Pydantic fact models, so the Python
side validates it straight into the frozen models a rule already expects. The protocol version
travels with it and a mismatch fails loudly. A native extension through PyO3 removes the
serialization step and stays available when profiling says the copy matters, but the process
boundary is the starting point because it keeps the kernel testable alone, keeps a crash out of the
interpreter, and needs no build toolchain wherever MCMR installs.

A rule runs when three things hold: its fact stream exists, its language matches or it is general,
and every dependency it declares was supplied. A rule failing any of them is skipped and counted,
never refused, so a Python-only repository and a run without a model backend both work without
deselecting anything. `docs/kernel.md` holds the task list and the definition of done for each
phase.

A provider states evidence or it states nothing. A field carrying a constant a rule then reads is
worse than a missing field, because the rule answers the same thing forever and usually that answer
is zero, which reads exactly like a clean repository. `tests/test_fact_variation.py` guards the
whole class: it builds every family over this repository and over a small written project holding
the shapes this one lacks, and a field that never takes a second value has to be in its ledger with
the reason, which separates a field no frontend writes from a literal every frontend states from a
field the corpus simply never moves. The ledger fails in both directions, so an entry left behind
after a field starts moving is a failure too.

A field that varies can still be unreadable, which is the gap `tests/test_fact_scope.py` closes.
Two checks, both mechanical and neither reading any prose. A record deriving `Relation` states two
ends of one edge, and the corpus has to show a value appearing on both sides somewhere, since a
relation whose columns never meet is a graph with no path and every component question over it
answers zero. And a rule whose settings declare a floor on distinct files has to read a family the
corpus shows one fact of holding that many files, which is read by asking the filesystem which of
the strings a fact states are paths rather than by trusting a field name. Both ledgers fail in
both directions. The second one holds three rules today, and finding the third of them is what the
check was for, since nobody had noticed that `ALL-DEPE0010` groups an external callable across two
files while reading a family built one file at a time.

## Execution

`RuleEngine.run` is asynchronous and every rule participates. Rules are grouped by their fact
stream, facts are grouped into chunks, and each chunk runs as one synchronous batch in a bounded
AnyIO worker pool. A batch invokes its rules, validates what they returned, and builds the
observations, so the event loop keeps only the asynchronous results. An asynchronous rule returns
its unstarted coroutine from the batch and the loop awaits it, which keeps model and backend work
on its own concurrency instead of holding a worker thread.

The worker count follows the interpreter. A build holding the GIL stays at one worker, since
threads cannot run Python rule bodies in parallel there. A free-threaded build scales to a ceiling
of six, which is where added workers stopped paying for themselves in measurement. Results return
in submission order, and the first failure inside the task group is re-raised with its own type so
a rule error reaches the caller as that rule's error.

Chunking mattered more than parallelism. One submission per fact made the thread handoff cost about
as much as the work it carried. Grouping facts into a small multiple of the worker count took a
43,200-invocation workload from 605 ms to 205 ms on one worker, and parallelism then took it to
86 ms on six. That is 7.3 times the original serial engine, of which 2.5 times is free threading.

Invocation itself avoids rediscovering its own contract. Each rule caches its signature, its
injected dependency names, and its subject parameter, then places arguments directly against the
cached signature instead of rematching them for every fact. `Signature.bind` was 38 percent of one
invocation before that change.

## Mock floor

The mock engine measures Python framework overhead only. It covers cold and warm discovery,
contract validation, typed fact planning, dispatch, result aggregation, and fix candidate planning.
It excludes parsing, filesystem traversal, graph construction, type inference, model inference,
subprocesses, and edit application.

This boundary makes the floor honest. Phase two can add provider costs independently and preserve a
clear performance budget for the framework itself.

## Phase two

The next phase implements provider protocols against these rule signatures. It starts with a shared
workspace, incremental invalidation, language-neutral source spans, Python semantic facts, and an
oracle comparison against the existing GE4M prototype, Archy, Pylint, Vulture, and Lizard behavior. Rust only
enters where profiling shows that Python orchestration or provider work cannot meet the target.
