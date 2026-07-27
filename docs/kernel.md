# Analysis kernel

The kernel is the Rust half of MCMR. It owns discovery, parsing, fact extraction, and the
repository graph. Python keeps rule authoring, policy, fixes, and reporting. The boundary is the
fact contract that phase one froze, so a rule never learns which half produced its evidence.

## Why Rust owns this half

Rule bodies are small. The work around them is not: walking a repository, reading and parsing every
file, resolving names, and building a graph. That work is where a Python implementation spends its
time and where a Rust implementation is several times faster with no loss of clarity. Rules stay in
Python because that is where they are read, reviewed, and experimented with.

## Transport

The kernel is a binary that answers one request and exits. The request names a root, an exclusion
set, and the fact families to build. The response is one JSON document whose field names match the
Pydantic fact models exactly, so the Python side validates it directly into the frozen models a
rule already expects.

A native extension through PyO3 removes the serialization step and stays available when profiling
says the copy matters. It is not the starting point: the process boundary keeps the kernel testable
on its own, keeps a crash from taking the interpreter with it, and needs no build toolchain in
every environment that installs MCMR. The protocol version travels in the response so a stale
binary fails loudly instead of producing facts a newer rule misreads.

## Dependency injection

Rules declare the fact they read as their first parameter. The catalog already derives that type
from the signature, so the planner takes the fact types of the selected rules, asks the kernel for
exactly those families, and passes each stream to the rules that requested it. A family nobody
selected is never built, never parsed for, and never serialized. That is the whole injection
system: a rule cannot receive evidence it did not ask for, and the kernel cannot spend time on
evidence nobody wants.

## Tasks and definition of done

### K1, the vertical slice

- [x] One Rust crate under `kernel/`, built, tested, and linted through chefe tasks
- [x] Versioned request and response protocol whose field names match the fact models
- [x] Repository discovery with exclusion globs and a source-suffix filter
- [x] Python frontend on the Ruff parser, one parse per file feeding every family
- [x] `ModuleFact`, `ImportBindingFact`, `FunctionFact`, `ClassFact`, `CommentFact`, `CallFact`
- [x] Fact families built only when the planner requests them
- [x] `mcmr check` runs the real catalog over a real repository
- [x] Rust unit tests over fixture sources, and a Python test that runs the kernel end to end
- [x] A differential test against Ruff for unused imports on this repository

**Done when** `mcmr check src` reports rule observations produced by the kernel, the unused-import
stream agrees with Ruff `F401` on MCMR's own source, and both suites stay green at full coverage.

K1 is done. `mcmr check src` reads 324 files, builds 2,662 facts in 23 ms, and runs 24,986 rule
invocations in 62 ms. Over GE4M's 740 files it builds 8,748 facts in 131 ms and runs 85,670
invocations in 178 ms. The unused-import stream agrees with Ruff exactly, at zero findings on this
source and at the same single finding on a fixture that has one. Reaching that agreement took three
fixes the oracle exposed: names used in annotations, in type aliases, and in type parameter bounds
all count as uses, and a name listed in `__all__` is a deliberate re-export.

### K1b, the rest of the source-derivable families

- [x] Symbols, attribute accesses, annotations, try blocks, comprehensions, collections, strings,
      literal groups, branches, enums, exceptions, method groups, parameters, prose, queries,
      runtime type checks, waivers, directories, dependency edges, Pydantic models, pytest tests
- [x] Project configuration read from the repository manifest
- [x] An evidence store for facts no parser can derive, read from `.mcmr/<FactName>.json`
- [x] A self-scan of MCMR by MCMR, with every true positive repaired

**Done.** 125 of the 155 deterministic rules run from source or configuration alone, and the
remaining 30 run wherever a project keeps the records they read. The self-scan reads 324 files,
builds 9,174 facts in 49 ms, and runs 39,466 invocations in 87 ms across 115 rules.

The scan found defects on both sides. In MCMR's source: two callables whose same-typed neighbours a
caller could transpose, a module constant other files imported, four predicate helpers that did not
read as predicates, and a missing setup task. In the rules themselves: swappable parameters counted
keyword-only arguments that cannot be transposed, the parameter extractor claimed to know uses it
had not resolved, rule modules named after testing were treated as pytest files, and a Python target
written as `py314` was not read. Every one is fixed.

### K2, the graph

- [x] Typed structural multigraph: repository, directory, file, module, class, function, method,
      property, attribute, variable, parameter, external boundary, unresolved symbol
- [x] Containment, definition, import, inheritance, call, and construction edges, each retaining
      every source site separately
- [x] Static resolution for lexical names, imported symbols, `self` and `cls` receivers,
      constructors, and builtins, leaving what it cannot prove visible as unresolved
- [x] `TYPE_CHECKING` branches excluded from the runtime structure
- [x] Node identity that survives an ordinary edit, shared with the oracle exactly
- [ ] Typed receiver resolution, which the oracle performs through parameter and variable
      annotations and the kernel does not yet
- [x] Package re-export resolution, so an import reaches the module that defines the symbol
- [ ] Graph views: neighborhood, metric, and repository projections a rule can request as a fact

**Done when** node, edge, and rendering counts match the Archy oracle on this repository, and
`ALL-ARCH0011` reports the same cycles through the kernel as it does through Archy.

Re-measured against the Archy fork's own graph engine on MCMR's 353 Python files, with the fork run
directly rather than from memory. **99.2% of Archy's node identities and 97.9% of its edges are
shared**, and define, import, and inherit match exactly: 2,809 definition edges, 849 import edges,
278 inheritance edges, all identical.

Import edges were 72.2% until this pass. The entire gap was one pattern: `from mypackage import
rule`, where MCMR pointed at the package the source names and Archy followed the re-export to
`mypackage.decorators`, the module that actually defines the symbol. Following it is what makes the
arrow point at the code that would have to change, so the graph now walks re-export chains and that
number is 100%.

What remains is one resolution feature and one naming difference. Archy resolves a receiver through
its declared type, so `subject.count_calls` becomes an exact call edge where the kernel leaves it
unresolved; that is most of the residual 88% on call and instantiate edges. The rest is the 27
nodes MCMR names differently, which are external symbols it classifies more coarsely.

One divergence is deliberate. A repository, a directory, and a file are identified as
`path:{kind}:{path}` rather than under a language, because a directory holding Python beside Rust
belongs to neither. Archy prefixes them `python:` because it only ever saw Python. The comparison
above normalizes that prefix before comparing.

### K2b, reading code rather than counts

- [x] `SyntaxFact`, one per declaration, carrying its exact source and a bounded navigable tree
- [x] A language-neutral node vocabulary a general rule can read without learning any syntax
- [x] The Rust frontend filling the same family through the same vocabulary
- [x] The native frontend filling it too, for C, C++, and CUDA
- [x] The TypeScript frontend filling it too

Every other family answers a question somebody already asked. A rule about how a project spells its
local variables, orders the clauses of a comprehension, or nests its branches needs the code
itself, and until now the only route to that was a `NodeRef` some fix happened to leave behind:
addressed nodes carry their exact text, but a `NodeRef` is a leaf with no children, and only
eighteen field names in the whole fact set carry one.

`SyntaxFact` closes that. One fact per declaration, carrying `source` as written and `tree` as a
navigable structure with `walk`, `of_kind`, `names`, and `depth` on it. So a rule can ask what a
function binds, what it calls, what literals it holds, and how deeply it nests, without parsing
anything:

```python
subject.tree.names("binding")      # ['bare']
subject.tree.names("call")         # ['name.lstrip']
subject.tree.of_kind("text")       # the literals, with their spans
subject.tree.depth                 # 5
```

Two decisions keep it affordable. The vocabulary is deliberately not a parse tree, because a
faithful one makes a general rule learn the syntax of whichever language produced it: twelve kinds
carry what a rule actually asks, and anything a language adds arrives as children rather than as a
kind nobody else has. And the tree is depth-bounded at six, deep enough to hold a call inside a
comprehension inside a branch and shallow enough to stay cheaper to send than re-parsing the file.
A rule that never asks for the family never pays for either, which is what the injection system was
built to do.

`ALL-NAMI0001` is the first rule to read code rather than counts, and it demonstrated the shape
immediately: its first run reported four class fields named `id`, which are interface names a
reader meets elsewhere rather than locals, so the rule judges callables only.

The vocabulary is enforced rather than merely documented. Every frontend passes each kind through
`syntax::known`, which returns the neutral kind for anything not on the list, so a frontend cannot
invent one by accident and leave a rule silently never matching. The Rust frontend fills the family
through that same door: 436 declarations from the kernel's own 15 files, and `ALL-NAMI0001` runs on
them unchanged, reporting fourteen two-character locals in the kernel's own Rust. One rule, written
once, reading two languages, is the whole point of the vocabulary being neutral.

The native frontend fills it now as well, which took mapping a grammar rather than an AST. The
tree-sitter tree names every shape it needs to parse C++, and several of those exist only to group:
the block a body opens, the list an argument sits in, the parentheses around an expression, and the
clause a `catch` or an `else` introduces. Those contribute their children in place and cost the tree
no depth, so `if (count > 0) { total = helper(count); }` arrives as a branch holding a binding
holding a call, exactly as the Python frontend states the same program. Three decisions are worth
naming because a rule turns on each of them. Parameters stay out of the tree, since `FunctionFact`
already carries them and putting them in would make a rule about local names answer differently for
this language than for any other. A comment is dropped, because the grammar hands one over wherever
a token can go and the comment family is what reads it. And an expression statement is located at
its own expression rather than at the semicolon that ends it, because `ALL-CONT0002` finds a
statement that only produced a value by matching the child covering the whole statement, and the
punctuation would have broken that match for every brace language at once.

What the tree costs is worth stating, since it is the most expensive family in the set. Over
MCMR's 357 Python files: every other family together is 102 ms and an 8.5 MB payload; adding the
trees takes it to 174 ms and 14.5 MB. Asked for alone the trees are 80 ms and 6.1 MB for 678
declarations. That is why it is a family a rule opts into rather than a field on `FunctionFact`.
Over 224 CUDA sources the native trees are 52 ms for 986 declarations, and `ALL-NAMI0001` reports
280 locals too short to say what they hold where it previously reported nothing at all.

### K2d, a family that answers for one language is a rule that answers for none

`CommentFact` was built by the Python frontend and by nothing else, so the whole `ALL-COMM` family,
including the work-marker rule, read an empty stream for Rust, C, C++, and CUDA. That is the worst
shape a rule can have. A rule reporting zero is indistinguishable from a clean repository, and the
catalog said the language was covered, so nobody would go looking. `SyntaxFact` was in the same
state for the native frontend and `CallFact` for Rust.

All three are filled now. The comment family is one shared reader over a per-language answer to the
two questions only the language can settle, which are whether a comment addresses a tool and whether
it is code rather than prose. Grouping, sizing, and addressing are the same wherever a comment
appears and are settled once. Finding the comments is not: a tree-sitter grammar hands them over as
nodes, `syn` keeps a doc comment as an attribute and drops the rest, and the token stream drops them
all, so Rust needs a lexical scan that steps over strings, raw strings, characters, and the nested
block comment this language alone allows.

Deciding whether a comment is commented-out code is done by parsing it, which is the only honest
answer and also almost all of what the family costs. Two things keep that affordable. A body is
handed to the parser only when it holds the punctuation its language cannot state code without,
which is a semicolon or a brace for the brace languages and one character wider for Rust, whose
blocks yield their last expression. And the likelier of the two parses runs first, since a
commented-out statement is far more common than a commented-out declaration. Together those took
the family from 154 ms to 56 ms over 224 CUDA sources with every finding unchanged.

What guards the whole class of defect is a test rather than a promise. `tests/test_language_coverage.py`
takes the reference frontend's answer over one fixture as what a general rule was written against,
runs the same fixture in six languages, and requires every other language to answer the same set. A
language that answers less has to be written into the gap table with its reason, so a hole is a
recorded decision and a new one fails the suite.

### K2e, a directory is not a language construct

`DirectoryFact` was the same defect one layer down, and worse, because it was not empty but
fabricated. The Python frontend pushed one directory fact per source file and filled it with
literals: `visible_entry_count` and `direct_module_count` were both `1`, `is_retained` was `true`,
`source_depth` was the raw component count, and the language was asserted to be Python for a
directory that might hold none. Three rules read that. `ALL-FILE0001` was unsatisfiable, since it
asks for a directory holding nothing and the provider said every directory held one thing.
`ALL-FILE0003` measured `1` for a folder of six siblings and stated it six times. `ALL-FILE0002`
ignored source roots entirely. And a repository with no Python in it got no directory facts at all.

The fix is where the evidence is. Discovery walks the repository and is the only thing that knows
what a folder holds, so it records directories as it meets them rather than deriving them from the
files it read, which is the only way a directory holding no source can be seen. One fact per
directory now, no language on it, and every field read off the tree.

Two of the fields needed a decision rather than a count. A source root is derived instead of
configured, being any directory named `src` together with the first ancestor of a package chain
that is not itself a package, which is the same boundary `Packages` and `Crates` already compute
module names against, so a configured list that nobody updates never enters the picture. And
whether a folder is a definition catalog is a question about what its modules declare, which every
frontend already answered in `ModuleFact`, so the directory family asks for that family alongside
itself and drops it again when the caller never wanted it, rather than parsing everything a second
time.

Skipping an excluded subtree instead of walking it and filtering the files afterwards took
discovery over the whole `~/projects` monorepo from **606 ms to 160 ms**, and the directory facts
went from 9,375 duplicates to 5,554 distinct directories. On MCMR's own tree the three rules now
report six real findings where they reported none, which are three genuinely empty directories
under `docs` and three folders holding more than twenty direct modules. Over `~/projects` they find
34 empty directories and 17 folders past that ceiling.

The scan found four more fields fabricated the same way, and K2f closes all four and builds the
test that would have found them.

### K2f, a fabricated field is a defect a test can find

Nine instances of one defect in a day is not nine mistakes, it is a missing test. A provider writes
a literal, a rule reads it as evidence, the rule's unit test passes on a hand-built fact, and in
production it answers the same thing forever. Usually zero, which reads exactly like a clean
repository. Nothing in the suite could tell the two apart, because every test in it either builds
the fact by hand or asks one repository one question.

`tests/test_fact_variation.py` is the test that can. It runs every family the kernel builds over a
corpus and asks, for each field of each family, whether it ever took a second value. A field that
never moves is written into a ledger with the reason, and the ledger fails in both directions, so a
newly frozen field fails the suite and an entry left behind after a field starts moving fails it
too. Three reasons are told apart on purpose, because they are three different things. No frontend
writes the field, so every fact takes the model default. Every frontend writes the same literal.
Or the field is derived and the corpus holds no shape that moves it, which is a statement about the
corpus rather than about the kernel.

The corpus is the part worth arguing about. This repository is the first half, because it is real
code nobody wrote to satisfy this test, and that is what makes a constant field evidence rather
than an artifact. What a repository cannot do is state a shape it does not hold, and no scan of one
project can tell that apart from a provider that fabricates. So the second half is a small written
project stating exactly the shapes this one lacks: a second manifest, so the configuration facts
have a second answer to give, an exception two ordinary modules import, local collections read
every way that settles or unsettles a representation, and a dispatch chain whose arms differ in
size. It deliberately does not try to reach every family, since a fixture written to move a field
proves only that the fixture moves it, and wherever a field stays constant the ledger entry says
which of the three reasons it is.

Today that ledger holds **160 fields and three families**. That number is the finding. 85 of the
160 are fields no frontend writes at all, 42 are a literal every frontend states, and the remaining
33 are derived and unexercised here. It also caught one more unsatisfiable rule, `PY-COLL0002`, whose
`pair_sequences` no frontend has ever filled, and one field that is derived from a flag it can
never hold, `AttributeAccessFact.is_inside_owning_class`, which the walk sets on a declaration
statement and then reads on the accesses of its body.

The four open cases are closed by deriving what each asserted.

`CollectionFact` reads one callable at a time. A candidate is a name a body binds exactly once with
a list or tuple literal, so every read of it is in that callable and can be counted, and each load
is either the iterable of a loop or a comprehension, the right side of a membership test, or
something else. `all_reads_are_iteration` and `all_reads_are_membership` compare the two counts
against the total, so one indexing read leaves both false and `PY-COLL0003` abstains rather than
recommending a form that would break. `values_are_unique` compares the literals as written, and
homogeneity now means one literal kind rather than merely being literal, which is what stops a
mixed `("json", 2)` from being recommended as a list. The family also stops reporting module
constants, which it never should have, since this file cannot see who reads them.

`ExceptionFact` became a repository-wide pass. Where an exception belongs is a question about every
module at once, so no per-file builder can answer it, and `kernel/src/exceptions.rs` reads each
module once, keeps what it declares and what it imports, and joins the two. A relative import is
resolved against the package of the module that wrote it, so the same `from .service import
OrderError` in two packages names two definitions. A package initializer, a module of nothing but
imports, a star import, and the defining module itself are all excluded, because none of them
proves a second module depends on the name. `defining_module` is now the dotted module rather than
the path, which is what the rule's own exclusion was comparing against and never matching.

`AutomationTaskFact` derives both claims from the command. Repository owned means running it needs
nothing but this checkout and the environment the manifest declares, so it is false when the command
runs somewhere else or as somebody else, when it installs into the machine or fetches from the
network, or when the program it runs is an absolute path or one under a person's home directory. An
absolute path in an argument is deliberately left alone, since a build writing to a scratch
directory every machine has is still carried by the clone. Noninteractive means nothing in the
command opens a session, which an interactive flag, an editor, a pager, and a debugger each do. The
task list is also read from every table chefe supports rather than from `[tasks]` alone, so one
capability two environments declare differently carries both commands and `ALL-LIFE0001` can see
that neither is canonical, which was a third condition the old provider could never fail either.

`BranchFact` arms carry the body they select. `statement_count` is how many statements the arm
holds and `returns_value` is whether it ends by handing one back, which is what separates a lookup
table written as control flow from branching that happens to key on a literal.

Over `~/projects` the two rules that were unsatisfiable now report real findings where they
reported nothing. `PY-COLL0003` finds 34 local collections whose proven use fixes a clearer
representation, out of 1,121 it reads and 135 whose reads settle anything at all, and `PY-EXCE0003`
finds 12 exceptions reused widely enough to move, out of 58 declared and 22 that two or more
ordinary modules import. On MCMR's own tree `PY-COLL0003` finds one, a six-element tuple of
credential names a loop is the only reader of, and `PY-EXCE0003` finds one, `Incomparable` in
`comparisons.py` reached independently from the CLI and from a test.

`ALL-LIFE0001` is the honest one to state carefully. All 72 tasks `~/projects` declares stay inside
the checkout and run unattended, so its answer there is still driven by the capabilities the
manifest never declares, exactly as before. The difference is that the two conditions can now fail,
and one manifest in reach makes them fail: the dotfiles project declares a `shell` task whose script
runs `sudo chsh`, which is reported as a command the machine rather than the repository carries.
Reading a task as a script rather than as a line is what found it, since a newline separates two
commands the way a semicolon does and the escalation is three lines down.

The exception pass costs about 2 ms on this repository's 489 files, which is the second parse it
performs, and nothing else in the request moved. The variation test reads the whole corpus twice in
about two seconds and adds that to the suite.

### K2g, a flag that reaches the wrong statements, and the oracle that let it through

`AttributeAccessFact.is_inside_owning_class` could never be true. The walk set the owning flag on
the `FunctionDef` statement and then read the accesses of its *body*, which the walk visits as
separate statements where the flag is gone. Every `self.x` inside every method therefore read as
being outside its owning class, and `ALL-ENCA0001` reported protected access from inside the very
class that owns the attribute. Over `research` that is 12,590 findings where 2,304 are real.

The walk now carries the innermost lexical class down into the bodies it encloses, so a nested
callable keeps the class holding it and a nested class takes over, which is what an innermost
lexical owner means. `self`, `cls`, `super()`, and the class's own name are owner access wherever
they are written. It also reads assignment targets, which `expressions` deliberately leaves out, so
a protected *write* from outside is reported the way Pylint reports it and the rule's own claim to
examine writes became true.

The differential oracle should have caught this and did not, because it asserted the set of file
*paths* matched rather than the set of findings. Both sides of a one-file fixture reduce to
`{"generated.py"}` whatever either reader answered. The work-marker case was weaker still: it
compared `CommentFact` spans, and one comment fact covers a whole file, so every fact starts on
line one and the containment held vacuously. Every oracle assertion now compares findings. Where a
rule answers per record the record is handed to it alone and the lines it counts are compared, and
where a rule answers for a whole declaration the declarations are compared, so a finding in the
wrong callable fails even when the total is right.

Two relations are pinned rather than tuned away. Pylint lets a subclass reach a base member by the
base's own name and MCMR does not under the strict default, so MCMR reports one finding more on
that fixture. And `ALL-COMM0006` opens on `#` and `//` alike while Pylint can only answer for
Python, so the relation there is strict containment.

Twelve more providers stated a constant where a rule read evidence, and eleven rules that could not
fire now do. `PY-COLL0002` derives the pair tables a callable binds and the lookup loops that read
them, reusing the read classification `local_collections` already needed. `PY-ENUM0005` reads the
enumeration a receiver is proven to hold, from a member, a constructor, a subscript, an annotation,
or a loop over the class, resolving `from enum import StrEnum as Base` and skipping a class that
states its own `__str__`. `PY-INTE0001` reads the block a check guards. `ALL-PARA0002` and
`PY-COLL0001` read every use of a parameter and say whether the reader recognized all of them, so a
name handed to a call leaves `all_uses_known` false and the rules abstain rather than guess.
`PY-TEST0011` groups sibling tests by the syntax left once their literals are removed, which is the
only way two tests differing in nothing but data can be found at all.

The ledger fell from **160 entries to 130**. Thirty-six came out because the field they excused now
moves over the corpus, and six went in for the call resolution a test's calls do not carry, which
are the same six `CallFact` already records as unwritten.

Three lists stay empty on purpose and say so in the ledger. `EnumFact.scopes`, `EnumFact.files`,
and `SymbolFact.typing_scopes` are questions about a package rather than about a file, so they need
a repository pass the way `ExceptionFact` has one. Two rules are unsatisfiable for a second
structural reason worth naming: `ALL-DUPL0002` and `PY-TYPE0007` ask for a value repeated across at
least two files, and a per-file family carries one path, so no fact either can ever read reaches
the floor. `PY-SQLA0005` asks for a `primary_key_first` operation this provider does not recognize.

### K2h, a per-file fact cannot answer a question about a repository

`ALL-ARCH0011` could never report a cycle, on any repository, ever. `DependencyComponentFact` was
built one file at a time and carried that file's imports with the source spelled as the path with
its separators swapped and the target spelled as whatever the import line wrote, so `flask/app.py`
arrived as `flask.app.py` pointing at `click` and `collections.abc` and `flask/__init__.py` arrived
carrying nothing at all. Every edge of one fact shares one source and no target is ever equal to
it, which makes each fact a star. A star has no cycle, so the rule answered zero for every
repository there is while `mcmr matrix` printed the real components off the same graph and
`mcmr coverage` recorded Pylint `R0401` as natively answered.

Two mistakes stacked, and only the second one is about spelling. A file cannot see what imports it,
so no per-file builder could have answered this whatever vocabulary it used. `kernel/src/modules.rs`
holds the shared index now, one pass over the graph giving the modules files declare and every
import arrow between two of them with the lines that state it, and `coupling.rs` reads the same
index rather than building its own. That is what makes the two families spell a module identically
by construction instead of by agreement. `DependencyComponentFact` is one fact for the repository,
derived after extraction beside `ModuleCouplingFact`, `OverrideFact`, and `SymbolReachFact`, and
`lib.rs` keeps all four out of the per-file pass so no frontend is ever asked for one.

On flask 3.1.3 the rule now reports the one component of 8 modules that `mcmr matrix` already
printed, where Pylint reports five `R0401` chains running inside it and names seven of those eight,
the eighth being `flask.testing`, which `flask/app.py` imports inside a method where Pylint's
cycle checker does not follow. On anyio it reports 3 components against Pylint's 17 chains, and
every module it names is one Pylint names too. On MCMR's own source, on GE4M, and on both under
Pylint the answer is zero from every reader. Over the whole `~/projects` monorepo it finds 34
components across 4,200 files.

The repository pass costs the graph, which is 14.6 ms over flask's 24 files, 34.9 ms over MCMR's
412, and 90.4 ms over GE4M's 740. Nothing else moved, since three families already needed the same
graph. The rule side got cheaper rather than dearer, because Tarjan was building its adjacency by
rereading the whole edge list once per node, which is 65 ms over GE4M and 8 ms once it is one pass.
The walk also carries its own stack now, since the deepest import chain of a monorepo is bounded by
nothing and the recursion limit is not a graph property.

`tests/test_fact_scope.py` is the guard that would have caught it, and it is two checks rather than
one because the defect had two halves. A record deriving `Relation` states both ends of one edge,
and the corpus has to show some value appearing on both sides, since a relation whose columns never
meet is a graph with no path and every component question over it answers zero. And a rule whose
settings declare a floor on distinct files has to read a family the corpus shows one fact of
holding that many, where which strings are paths is settled by asking the filesystem rather than by
trusting a field name. The second check found a third rule nobody had listed: `ALL-DEPE0010` groups
an external callable across two files while reading `CallFact`, which is one fact per file.

What was measured and rejected is worth recording too. The general form of this guard is to run
every deterministic rule over the corpus and require its answer to move, which is the variation
test lifted from fields to rules. Over this repository 105 of the 176 rules whose family the corpus
fills never fire, and almost all of those are a clean repository rather than a broken rule, so the
ledger would be four fifths noise and the real entries would be invisible inside it. The two
structural checks cost nothing and name only real defects, which is why they are the ones that
landed.

### K2c, the metric projection, and why a layering contract is not a config file

A layering contract in a config file rots. Somebody adds a legitimate edge, the check fails, they
widen the rule, and within a year the file describes the code instead of constraining it. Almost
everything such a file buys is already in the module graph, so `ModuleCouplingFact` derives it every
run and it cannot drift away from what the code does.

The family carries four counts per module and no judgment at all. Afferent and efferent coupling
are the distinct modules of this repository that import it and that it imports, which give Martin's
instability `I = Ce / (Ca + Ce)`. Declaration and abstract declaration counts give abstractness
`A`, and the two place the module against the main sequence `A + I = 1`, whose distance
`D = |A + I - 1|` names the concrete module everything leans on and the abstraction nothing took
up. The coupling of every imported module travels inside the importer's own fact, because the
Stable Dependencies Principle compares two stabilities across one arrow and a rule sees one module
at a time.

`ALL-ARCH0012` reports an import pointing at a less stable module, which is a layering violation
found without anybody naming a layer. `ALL-ARCH0013` reports the zone of pain and `ALL-ARCH0014`
the zone of uselessness.

What each frontend can see, since abstractness is the half that is not universal:

| Language | What counts as a contract | What the kernel misses |
|---|---|---|
| Python | a class deriving `ABC` or `Protocol`, naming `ABCMeta` as its metaclass, or declaring an `@abstractmethod` | a class abstract only because an ancestor left a method unimplemented, which needs the chain rather than the class |
| Rust | a `trait` | nothing, since a trait is the only contract this language has |
| C++ and CUDA | a type declaring a pure virtual, read from the declarator rather than from the text | a contract expressed as a template parameter, which has no declaration to point at |
| C | nothing | the language has no construct, so every C module reads as fully concrete |
| TypeScript | an `interface`, an `abstract class`, and a `type` alias, since each states a shape and hands over no implementation of it | a class abstract only because an ancestor left a member unimplemented, and a shape a generic parameter stands for, neither of which has a declaration to point at |

A module is what one file declares, which is the unit the Archy oracle also uses. A nested Rust
`mod` and a C++ namespace are module nodes too, so what either imports is folded onto the file
holding it rather than counted as an arrow between two halves of one source file.

Two defects in the Rust frontend surfaced the moment the counts were read, both of which inflated
the crate root. `use super::*` inside `mod tests` resolved against the file rather than against the
module doing the reading, so every test module in the crate pointed at the crate root, and
`use crate::families` recorded the edge against the path prefix rather than against the module the
line names. Sixteen phantom dependents on the kernel's own crate root are gone with them.

Against Archy on MCMR's own source the two agree exactly on all 409 modules and on 873 of 878 import
edges. The five that differ are the five imports stated only inside a `TYPE_CHECKING` block, which
MCMR omits because they do not exist at run time and Archy keeps. Instability agrees on 404 of 409
modules and the five that differ are exactly the endpoints of those edges. Archy reports three
Stable Dependencies violations where MCMR reports one, and both extra ones exist only because a
`TYPE_CHECKING` import raised the target's instability past its importer's. The test asserts
containment and re-derives those edges from the source rather than hardcoding them.

### K3, the LLM graph view

- [ ] Compact text projection sized for a model context, with a node ceiling and a focus selector
- [x] D2 rendering for the human view and JSON for the complete artifact
- [x] Stable ordering so two runs over unchanged source produce identical output
- [ ] Evidence bundles that carry a bounded neighborhood rather than a whole repository

K4 delivered the middle two ahead of this milestone. `mcmr diagram` renders D2 and Mermaid, `mcmr
matrix` and `mcmr impact` render text and JSON, and all of them order by name through a condensation
of the cycles, so two runs over unchanged source agree byte for byte. What is still missing is the
part K3 is actually about, which is bounding a projection to a neighborhood and having it say what
it left out. `--limit` truncates a matrix today without reporting the truncation, and that is the
gap rather than the rendering.

**Done when** a model rule receives a bounded neighborhood for one nominated node, the same input
produces the same bundle twice, and the bundle names its own truncation.

### K4, Pylint, Pyreverse, and Symilar

- [x] An account preserving every Pylint identifier, symbolic name, and source checker, each marked
      native, delegated, adapted, inapplicable, or unavailable with a written reason
- [x] Native implementations for the design, classes, variables, and imports checkers, which are
      the ones that need the graph rather than local syntax
- [x] Pyreverse parity: class and package diagrams from the same graph, in D2 and Mermaid
- [x] Symilar parity: token-normalized clone detection producing locations, with the semantic
      judgment left to `ALL-DUPL2003`
- [x] Differential tests against Pylint, Pyreverse, and Symilar on this repository and on GE4M

**Done when** the account covers every Pylint message, every native message matches Pylint on
the differential corpus, and the diagram and clone outputs match their oracles.

Where MCMR and an oracle disagree, the test asserts the relationship rather than the equality, so
the difference stays visible instead of being tuned away.

| Oracle | Agreement | Difference, and why it is intended |
|---|---|---|
| Symilar, locations | exact files and lines | none on a verbatim paste |
| Symilar, share | `37.04` against `37.04` | none |
| Symilar, renamed locals | MCMR reports, Symilar is silent | Symilar compares stripped text where MCMR compares normalized tokens, so MCMR is the wider reader and the general relation is containment |
| Pyreverse | every box, member, and inheritance line | Pyreverse infers attribute types where MCMR prints what the source states, and MCMR prints UML visibility sigils where Pyreverse prints none |
| Archy, churn and co-change | exact on all 112 ranked files and every surfaced pair | none |
| Archy, hotspot ranking | top 1 identical, top 5 identical as sets, 17 of 20 overlapping | Archy weighs churn by a cyclomatic sum where MCMR weighs it by lines, which is Tornhill's own proxy |
| Archy, module graph | 391 modules, impact sets identical | 5 `TYPE_CHECKING`-only edges MCMR omits because they do not exist at runtime, re-derived from source by the test rather than hardcoded |
| Pylint, 9 override messages | exact | none |
| Pylint, `arguments-renamed` | exact, 6 of 6 on the fixture and 9 of 9 on the wider shape corpus | none |
| Pylint, `signature-differs` | exact, 1 of 1 on the fixture and 2 of 2 on the wider shape corpus | none |
| Pylint, `arguments-differ` | exact on every shape but one, 9 of 9 on the fixture and 15 against 13 on the wider corpus | Pylint compares the ordinary parameter list its own parser builds and keeps positional-only parameters in a separate list the comparison never opens, so an override that drops one is silent there and reported here |

All three divergences shared one root cause, and it is closed. `graph.rs` Parameter nodes carried an
ordinal and an annotation but neither a default nor a kind, so an added parameter could be required
or optional and a trailing name could be a variadic or an ordinary parameter spelled `args`. A
`ParameterKind` naming the five ways an argument binds, plus `has_default`, now travel from every
frontend through `OverrideFact`, and the three rules read the signature the way each message means
it. The `args`/`kwargs`-tail heuristic that stood in for the missing kind is gone.

What is left is one gap in the oracle rather than in MCMR. A positional-only parameter is a slot a
caller has to fill and a name no caller can pass, so MCMR counts it toward the arguments and never
toward the names. Pylint counts it toward neither.

The account is in and it covers all 389 messages Pylint 4.0.6 emits, not the 422 this page
used to claim, which was a number from an older release that nobody had rechecked. Reading the
registry rather than a remembered figure is the point: the inventory is frozen from Pylint's own
checkers into `mcmr/data/pylint.json`, and a message a future release adds falls through to
"unaccounted" rather than inheriting a comfortable default.

Today that reads **22 native, 269 delegated, 6 adapted, 19 inapplicable, 73 unavailable**. The
large delegated share is the honest answer rather than a dodge, and it breaks down exactly: 61
messages Ruff implements under the very same symbol, 45 it implements under a name of its own or
another tool in the stack owns outright, and 164 whose whole checker belongs to Ruff. Every
delegation names the rule that takes it. An adapted entry is where MCMR asks a different question
about the same concern, such as answering `too-many-instance-attributes` by judging what the
attributes are rather than counting them.

Inapplicable is the state that closed an accounting error. Eighteen messages in the `main` checker
report on Pylint's own run, a plugin that would not load or a configuration section that would not
parse, and `use-symbolic-message-instead` asks a pragma to spell a message by name. Calling those
unavailable conflated "we cannot do this" with "this was never about the code", understated the
coverage, and buried the real gaps underneath nineteen entries nobody could ever close.

Unavailable is split by what each entry is missing rather than left as one shrug. Fifty-two
messages need the inferred type of an expression, four need to know which assignment reaches a use,
six need the sub-patterns of a `match` case, and two need the installed environment. The rest name
one piece of evidence each: an operator on a comparison node, a `global` statement the neutral
vocabulary has no node for, the parameter kinds of a callee at its call site, or two fact families
in one rule where a rule receives exactly one.

Reading Ruff's own inventory back rather than trusting the frozen same-name set caught twenty-one
wrong entries in it. Sixteen were rules Ruff had renamed while keeping Pylint's code, such as
`invalid-bool-returned` becoming `invalid-bool-return-type`, and those are now stated delegations
that name the code. Three claimed a Ruff rule that does not exist: `not-a-mapping` and
`not-an-iterable` need inference and nobody answers them, and `no-method-argument` is a real gap,
since Ruff's `N805` reads the name of a first parameter and says nothing when there is none. The
last two named symbols no Pylint release in the inventory emits, so they delegated nothing at all
while reading like coverage.

`mcmr coverage` prints the whole account and narrows by tool, group, or state.

### K4c, provenance on the rule rather than in a ledger

The ledger was a module named after one tool inside an engine that fronts six languages, and it
carried a second copy of provenance the 277 rule docstrings already stated in their `References`
sections. Two copies of one fact drift, so the arrow is now turned around. A rule states which
upstream rules it generalizes, and the account of any tool is derived from those statements.

A reference to an upstream rule is one line of the `References` section reading
`relation tool identity [identity]`, where the relation is `Generalizes`, `Adapts`, or `Cites`, and
an identity is a code the tool spells or the rule's symbol. `Generalizes Pylint R0904
too-many-public-methods` claims that message natively, `Adapts` claims it as a different question
about the same concern, and `Cites` names prior art and claims nothing at all. A reference to a
published work reads `relation "Title"` with an optional locator behind a comma, and a bare URL
line attaches to the entry above it. Nothing else parses, so the section holds no prose at all.
`SYSTEM.md` states the whole grammar as the one expression `ReferenceParser` runs.

The relation word is what makes the tool half exact rather than clever. Without it, nothing
distinguishes `Vulture documentation` from a rule identity except a heuristic, and any heuristic
that settles it eventually settles it wrongly. With it, a tool named inside a sentence can never
become a coverage claim by accident, which is precisely the failure that put a rule in the ledger
as both native and delegated to Ruff on the same message. The quotes do the same job for the
literature half, where the failure was the same shape: free prose made `Fluent Python` and
`Luciano Ramalho, Fluent Python` two works, so no influence could be counted. `mcmr/data/works.json`
registers every citable work with the title that is its key, its kind, its author, and its link, and
`InfluenceReport` reads the table straight off the catalog.

What a rule cannot state is where a gap comes from, because a gap is a statement about the upstream
tool rather than about any MCMR rule: no rule exists to carry it. So the reasons live beside the
inventory in `mcmr/data/<tool>.gaps.json`, one statement per set of symbols or per group, with the
default that reports anything unnamed as unaccounted for. Adding a tool is now two data files and no
code.

`mcmr/data/<tool>.json` is the frozen inventory, and `mcmr.inventories` regenerates each one from
the tool itself. Pylint uses its own `PyLinter` message store, Ruff uses `ruff rule --all`, Clippy
uses `clippy-driver -W help`, clang-tidy uses `--list-checks`, cppcheck uses `--errorlist`, and the
two ESLint profiles read their package registries through Node. The suite re-derives every
inventory whose upstream executable can coexist with this environment, so a renamed or retired
rule turns the reference leaning on it red. The conda cppcheck package currently cannot coexist
with the free-threaded Python 3.14 ABI, so its captured parser test remains live while local
re-derivation skips honestly.

Turning the arrow around changed no Pylint arithmetic, which was the point. The account still reads
22, 269, 6, 19, 73 over the same 389 messages, and the same 28 covered messages name the same rules.
The table now accounts for seven tools and 3,538 upstream rules. Every tool profile also states its
language boundary. A general claim counts only when the provider ledger proves that the fact family
exists for every language the tool reads, so a true Python comparison cannot silently claim native
or TypeScript coverage.

### Differential testing against Pylint

- [x] A Hypothesis oracle for every message MCMR claims to answer with Pylint's exact semantics
- [x] Pylint pinned as a development dependency at the version the frozen inventory was read from
- [x] The same treatment for the messages that land as K4 completes

Pylint runs as a real oracle rather than as a remembered claim. `test_unused_import_agrees_with_pylint`
generates a module from a Hypothesis strategy that decides which imports it will actually use,
writes it out, runs Pylint with only that message enabled, runs the MCMR rule the account names, and
asserts the two sets are equal. The strategy states the expected answer as it builds the source, so
the property has an opinion of its own rather than only comparing two readers of the same text.

Writing it found three wrong mappings immediately. `unused-import` and `misplaced-future`
pointed at each other's rules, and `wildcard-import` pointed at a TypeScript rule, which cannot
answer a Python message at all. The old test only checked that a claimed identifier existed, which
all three did. A claim that merely names something real is not a checked claim, so the coverage test
now requires a Python message to name a rule whose scope could answer one, and `wildcard-import`
became a delegation to Ruff's `F403`.

Two other claims were overclaims and are now recorded as such. `duplicate-code` named the semantic
duplication rule, but nothing fills the clone groups that rule reads, so claiming it would be
claiming a rule that never runs; it and the `similarities` checker are unavailable until Symilar
parity lands. `misplaced-future` became adapted rather than native, because Pylint reports a
`__future__` import that is not first while MCMR reports one no supported interpreter needs at all.

### Profiling the kernel

`perf` is unavailable here, since `perf_event_paranoid` is 4 and lowering a machine-wide security
setting to read a profile is not a trade worth making. A benchmark suite is the better answer
anyway, because it lives in the repository, runs on any machine, and reports a distribution rather
than one stopwatch reading, so a change of a few percent is legible instead of lost in noise.

Reaching it needed one structural change. The kernel was a single binary, so nothing could measure
a part of it, and it is now a library with a thin binary over the top. `mcmr_kernel::run` holds
what the executable used to, and `main.rs` is twenty lines of reading standard input. That split is
worth having on its own: a benchmark, a future native extension, and any other consumer all need
the library rather than the process.

`chefe run kernel-bench` measures each phase over this repository's own Python, in process, so the
numbers are the work rather than the work plus a process spawn and a six megabyte write to a pipe.

| phase | time |
| --- | --- |
| parse every file | 2.2 ms |
| index every file for spans | 0.17 ms |
| `ModuleFact` | 3.7 ms |
| `ClassFact` | 3.5 ms |
| `TypeAnnotationFact` | 4.7 ms |
| `FunctionFact` | 6.4 ms |
| `ImportBindingFact` | 7.8 ms |
| `StringExpressionFact` | 7.9 ms |
| `AttributeAccessFact` | 8.6 ms |
| `CallFact` | 13.4 ms |
| `SyntaxFact` | 40 ms |
| build the repository graph | 15.9 ms |
| summarize reach from the graph | 2.5 ms |
| serialize the syntax trees | 5.7 ms |

The first line is the surprise. **Parsing is 2.2 ms and everything else is what we do afterwards.**
`CallFact` costs six times the parse and `SyntaxFact` costs eighteen times it, so the parser is not
where any optimization lives.

Where it does live, found by removing one thing at a time from the most expensive family. Building
the trees with no `text` and no `span` on any node takes `SyntaxFact` from 40 ms to **22 ms**, so
copying source and computing line and column positions are together about 45% of the family. The
split between those two was inside run-to-run variance on this machine, so both are worth trying
and neither is proven dominant yet. Two shapes to try: an interior node's text is fully contained
in its parent's and in the fact's own `source` field, and `Source::span` runs two binary searches
plus a column scan for every node when the traversal visits offsets in nearly sorted order and
could carry a cursor instead.

Third on the list, and independent of all that, the graph pass parses every file a second time
after extraction already parsed it, which is 2.2 ms of its 15.9 ms and about 16% of the combined
facts-and-graph path.

### Parallel extraction

One file's facts never depend on another's, so the only thing keeping extraction sequential was the
shared map it wrote into. Each file now fills its own map on a rayon worker and the maps merge
after, which costs one allocation per file and buys every core the machine has.

On this repository's 357 Python files, extraction went from **52 ms to 14 ms**. Over the whole
`~/projects` monorepo it reads 11,373 files into 300,216 facts in 5.7 seconds of extraction and
12.9 seconds wall.

End-to-end `mcmr check` did not move, and that is the useful part of the result. It sat at 1.15
seconds before and sits there now, because the kernel was never the bottleneck for a repository
this size. The win is real and it shows at scale rather than in the inner loop.

Determinism is the thing to be careful about, so it is tested rather than asserted. Documents
arrive sorted and rayon keeps their order through the collect, so the merged streams are identical
to what one thread would have produced. A first check appeared to show six different answers across
six runs, which turned out to be the timing fields inside `stats` and was equally true before any of
this was parallel. The test compares the facts.

### What one request costs on the Python side

Measured rather than assumed, over 357 files and 5,336 facts:

| kernel work | 14 ms |
| spawn and pipe | 41 ms |
| JSON decode | 31 ms |
| Pydantic validation | 67 ms |
| importing `mcmr.cli` | 189 ms |
| discovering 250 rules | 47 ms |

Two things follow. Pydantic's core is already Rust, so the 67 ms is Rust building 5,336 Python
objects rather than slow validation logic, and moving it into our own Rust would not remove it
because the objects still have to exist for a rule to read them. And a PyO3 extension would remove
the middle two lines, which is 72 ms, or about 6% of a 1.15 second run.

Handing Pydantic the bytes instead of decoded dictionaries does help, at 45.7 ms against 76.4 ms
for the same result, and the whole saving is not calling `json.loads`, since a list adapter over
already-decoded dictionaries costs the same as validating one fact at a time. Capturing it needs a
model built per requested family set, which `create_model` cannot express in a way a type checker
can follow, and the house forbids the suppressions that would hide that. It was written, measured,
and backed out. It becomes clean when the kernel emits each family as separately addressable bytes.

Free threading does not help here either. Validation across families runs 45.9 ms serial, 41.5 ms
on four threads, and gets worse beyond, because building Python objects contends on the object
model whatever the GIL is doing. The engine already uses free threading where it does pay, which is
running rules in parallel.

The import cost is close to inherent. Defining 162 fact models costs 117 ms because each one builds
a Pydantic core schema, and the eager rebuild that keeps two free-threaded workers from racing
inside Pydantic adds 18 ms. That is the price of the frozen fact contract, paid once.

### What the injection system already optimizes, measured

The question was whether graph generation could be sliced to what the active rules need. The
measurement says the family level already does this, and says where the remaining cost actually
is. Over MCMR's 357 Python files:

| | cost |
| --- | --- |
| parse and walk floor, no families | 6 ms |
| `SyntaxFact` | +72 ms |
| `CallFact` | +16 ms |
| `ImportBindingFact` | +10 ms |
| `FunctionFact`, `StringExpressionFact` | +9 ms each |
| `AttributeAccessFact` | +8 ms |
| `TypeAnnotationFact` | +7 ms |
| every remaining family | +1 to 3 ms each |
| the whole graph | 17 to 21 ms |

Each family costs only what it costs, and not asking for one saves exactly that, which is the
injection system working. Slicing the graph by edge kind would save from the 17 ms, and both of
its consumers today need all of it: the reach fact credits an owner through type and member-access
edges, which is what took its false positives from 177 to zero. Building that knob now would add a
setting that saves nothing until the design structure matrix lands and asks for imports alone.

What the measurement did find is a real inefficiency. Facts alone are 78 ms and the graph alone is
30 ms, and asking for both is 108 ms rather than something closer to 85, because the graph pass
parses every file a second time after extraction already parsed it. Sharing one parse across both
passes is worth about 16% of the combined path, and unlike edge slicing it needs no new setting.

### The identifier scheme

A rule is identified as `{SCOPE}-{FAMILY}{NNNN}`, and the lane owns the leading digit of the
number: deterministic writes `0`, GLiNER writes `1`, and a judgment writes `2`. The catalog rejects
a file numbered against its own lane rather than accepting it, so the scheme is enforced instead of
observed.

It became necessary rather than being designed. `general/llm/errors/r0001` and
`general/deterministic/errors/r0001` both derived `ALL-ERRO0001`, because the lane was parsed out
of the path and then discarded, and the catalog refused to build until one of them moved. Reserving
the digit makes that collision impossible.

It also earns its keep for a reader. A deterministic rule gives the same answer twice, a GLiNER
rule asks a small extraction model, and a judgment asks for an opinion, and those are three
different things to trust. `ALL-ERRO0001` and `ALL-ERRO2001` now say which they are without anyone
opening the catalog. Sixty-three files moved to fit, all in the two non-deterministic lanes, and
every deterministic identifier is unchanged because those already began with zero.

### Generalizing what Ruff only does for Python

Ruff ships 968 rules and every one of them is Python. A good share encode engineering ideas that
are not about Python at all, and MCMR reading six languages can run those ideas everywhere without
duplicating the Python implementation. Reviewed by linter, the seam is `flake8-bugbear`,
`flake8-bandit`, `flake8-boolean-trap`, `tryceratops`, `flake8-return`, `flake8-todos`,
`flake8-print`, and `flake8-blind-except`: swallowed errors, blind catches, flag arguments,
hardcoded credentials, weak hashing, debug artifacts left behind, a raise that drops its cause, and
a superfluous else after a jump are all the same defect in Rust, TypeScript, and C++ as in Python.

`ALL-PARA0003` is the first of them, generalizing `FBT001` and `FBT002`. It reads `FunctionFact`,
which the Python, Rust, and native frontends all fill with parameter types, so one rule runs on
three languages the day it lands. On this repository it reports nothing in the Python and CUDA it
was pointed at, and six real flag arguments in the kernel's own Rust, including a `reachable: bool`
and an `inside_loop: bool` that a caller passes as a bare `true`.

### K4b, cross-language seams

- [x] Artifacts a manifest, an attribute, or a macro declares in one language
- [x] References that reach them from another, counted only where the name is a literal
- [x] Rules over the seam: one side wired, and how many languages cross it
- [x] Routes, where a client names a path a server declares
- [ ] Protocol shapes, where two languages share field names across a serialized boundary

A route has no general detector, and looking for one is the mistake. A path is declared by a
decorator in FastAPI, by a call in Express, by a builder in Axum, by an attribute in Actix, by a
directory name in SvelteKit and Next, and by a prefix composed at mount time in all of them. What
generalizes is the fact, not the extraction: a route carries a method, a path, and the framework
that declared it, and each framework has its own small adapter. The convention-based ones are not
in the source at all, so their adapter reads the directory layout.

Two things keep this honest. A reference is only claimed where the other side states the same path
as a literal, which is the rule the interop scan already uses, and a route a mounted router
composes a prefix onto says so, because its declared path is not the path it serves and every rule
declines to judge it. A parameterized route is skipped for the same reason: `/users/{id}` and
`/users/7` are different strings and no lexical reader can prove they are the same route.

Three rules read the set rather than one route at a time, because a duplicate, a route nothing
reaches, and a path that disagrees with its neighbours are all statements about the set.
`ALL-ROUT0002` carries the guard that matters most: a repository where nothing names any declared
route has its clients elsewhere, so it reports nothing rather than reporting every route it has.
On the AIZK repository this finds 20 routes across a SvelteKit frontend and a FastAPI service,
with reference counts on each, and all three rules pass.

**Done when** every seam in this repository is found and named. Today that is the `mcmr-kernel`
binary Cargo declares and Python spawns, and the `mcmr` console script the project manifest
declares. Both are reported reached, each crossing one language boundary.

### K5, incremental and multi-language

- [x] A TypeScript frontend on the oxc parser, filling the same families as the Python one
- [x] TypeScript rules for what its own linters do not own: wholesale re-exports, relative import
      depth, constructs that survive type stripping, and escape hatch density
- [x] A Rust frontend on `syn`, filling the same families and emitting the same nodes and edges
- [x] One C, C++, and CUDA frontend on the tree-sitter C++ grammar, filling the same families
- [ ] Demand-driven queries with an invalidation key per fact
- [ ] Persistent cache under the XDG cache directory

TypeScript is in. 111 files of a real project parse with no failures into 883 facts, and the
general rules run on them unchanged: `export` is what public means, a `#name` member is private,
and a relative import is the project-owned one. The Python and TypeScript frontends share every
fact family, which is what makes one rule answer for both.

### The TypeScript graph frontend

The fact half landed first and the graph half did not, so `graph.rs` skipped every `.ts` file and
everything downstream of the graph was blind to the language: no `ModuleCouplingFact`, no class or
package diagram, no design structure matrix, no impact set, and no `OverrideFact`. That is closed.
The frontend walks the same oxc parse through the parser's own visitor, so a construct it says
nothing about is still descended into and the calls inside it are still recorded.

A module is named by its own path with the suffix removed, because every specifier this language
resolves is a path and a name that reads back as one is the name resolution already has to compute.
Settling a specifier is three rules rather than a guess. A relative specifier walks from the file
that wrote it and usually leaves the extension off, so `./thing` is tried as `thing.ts`,
`thing.d.ts`, `thing/index.ts`, and `thing/index.d.ts`, and a specifier written `./thing.js` names
the source that emits it. A specifier a `tsconfig.json` maps takes the target that mapping states,
following the `extends` chain and reading through the comments and trailing commas every editor
writes into that file, which matters because a framework states its aliases in a generated config
the checkout inherits. Everything else names a package a manifest installs, and the frontend
attaches those itself rather than sending them through resolution, since the import line already
said where they come from.

Re-exports are followed the way they are for Python, so `import { rule } from './index'` against a
barrel that says `export { rule } from './decorators'` points at the module that writes `rule`
rather than at the one line handing it on. A `export * from` target is remembered too, and a
`export default class Widget` is reachable under whatever name the importer chose, because the
declaring module records what `default` stands for and the importing binding walks that one step.

Parameters carry both facts a signature states. Every position binds positionally, since this
language offers no way to name an argument at a call site, and a `...rest` swallows the tail. What
a caller may leave out is written two ways, as a default and as the `?` that makes a position
optional, and both mean the same thing to anybody comparing two signatures, so both set
`has_default`. A constructor parameter carrying an access modifier or `readonly` declares a field
of the class as well, and nothing else in the class body says so.

What it cannot see is worth stating, because each of these arrives as `unresolved` rather than
being dropped. A member reached through a value whose type the kernel never inferred stays
unresolved, which is the same gap the Python frontend has and is most of what remains. A relative
import of a `.svelte` component, a generated `.js`, or a `.json` names a real file this kernel was
never asked to parse, so the import edge points at an unresolved node rather than pretending the
path is a package. An ambient type a package or a `lib` declares, such as `HTMLElement` or
`D1Database`, is unresolved for the same reason: the declaration lives in `node_modules`. The
closed sets the language itself owns are not in that count, so `Record`, `Promise`, and `console`
resolve as external and a type parameter resolves to nothing at all, being a binder rather than a
name any declaration answers.

On a 113-file SvelteKit and Cloudflare Workers project this reads 113 modules, 115 named types, 74
functions, 98 methods, and 193 parameters into 2,144 nodes and 4,945 edges, with 243 import edges
landing exactly, 115 leaving for a package, and 132 naming a `.svelte` or generated file. Every
`ModuleCouplingFact` the repository can state is there, so `ALL-ARCH0012` through `ALL-ARCH0014`
judge it: the logging module carries 21 dependents and no abstraction at all, which is the zone of
pain found without anybody naming a layer. On the AIZK front end it reads 61 modules, and the
generated API types module reports 120 declarations of which all 120 are contracts, which is what a
module of nothing but type aliases should say.

What it costs is the honest number. Over those 113 TypeScript files the graph pass goes from 0.2 ms
to 8.7 ms, which is about 77 microseconds a file, and extraction does not move. Over the whole
`~/projects` monorepo, where TypeScript is a couple of hundred files among four thousand, the graph
pass goes from 3,534 ms to 3,754 ms and gains 6,503 nodes and 17,232 edges.

Rust is in, on `syn`. `pub` is the visibility keyword, `pub(crate)` is internal, an `impl` block
holds the methods of the type it names, a derive is an implementation the compiler writes, and
`use` is the import. A module is named from the directory holding its crate root, so
`packages/mcmr/kernel/src/graph.rs` is `kernel::graph` and every `crate::`, `self::`, and `super::`
path is rewritten against that. On the kernel's own twelve files this resolves 2,123 edges exactly,
1,617 to declared external crates, and leaves one unresolved, which is a call through a local
binding that no static rule can follow. The general rules run on it unchanged, and the
unreferenced-public-declaration count is zero, the same answer they give for Python.

The honest caveat is the corpus. All the Rust in this repository is the kernel itself, so the
frontend is partly validated against its own author. What guards against that is the shared
vocabulary rather than the tests: a rule written for Python reads the Rust facts without knowing
which language filled them, so a frontend that fills them wrongly produces findings that read
wrongly.

### What Rust rules judge

Five rules read one `RustSurfaceFact`, which carries what a module borrows, what it pins, and what
it copies. Those three arrive together because they are one decision seen from three sides: a
lifetime is what borrowing costs in the signature, a clone is what not borrowing costs at run time,
and a `'static` is what pinning costs forever. A rule reading only one of them would push a project
straight into another.

`RS-LIFE0001` reports an annotation elision would have produced identically, and claims only the
two arrangements syntax alone settles. A lifetime that never reaches the output is always elidable,
since elision gives each input its own and tying them together only restricts the caller. A
lifetime the receiver carries and the return states is always elidable, since elision hands every
elided output the receiver's lifetime. The third arrangement, an output lifetime coming from one
input with no receiver, is left alone: it turns on how many lifetime positions the inputs hold in
total, and a bare `Node` hides one where `&str` shows it, so the arity lives in the type
definitions rather than in the signature. Guessing would mean reporting a signature that does not
compile without its annotation.

`RS-LIFE0002` reports `'static` only where it demands. A parameter typed `&'static str` cannot be
handed a name read from a file and a field typed the same way cannot store one; a return typed
`&'static str` promises the caller more than it had to and forecloses nothing. Where the pin sits
is what decides whether it costs anything, so a lookup table handing back a name is never reported
and a signature demanding one always is.

The provider states positions and the rules decide what they mean. An earlier draft had the kernel
answer "is this elidable" directly, which the catalog's own contract test caught: a rule that reads
back a Boolean the provider already decided has computed nothing. Where a lifetime appears is
something only a parser can see; what the arrangement means is a judgment, and the two belong on
opposite sides of that line.

`RS-LIFE0003` and `RS-OWNE0002` are measurements rather than defects, and they are meant to be read
together. Driving annotations to zero by owning everything moves the cost into allocations, and
driving allocations to zero by borrowing everything moves it into signatures, so the standard
profile puts a ceiling on both rather than a prohibition on either. `RS-OWNE0001` is the one place
where owning instead of borrowing is usually wrong, since a copy inside a loop is paid again on
every pass.

Run against the kernel, these took its own lifetime count from eight to four. Two went when edition
2024's return-position capture made `+ 'text` unnecessary on an iterator, one went when a function
handed back a range instead of a borrow of the tree, and one went when two functions that always
ran together became the single question their caller actually had. The four that remain borrow into
a tree-sitter or oxc parse tree, which is the case with no other answer. Zero `'static` demands and
zero elidable annotations remain; the clone counts still exceed the standard ceiling in the graph
builder and the Rust frontend, which the rules report and nothing hides.

C, C++, and CUDA are in as one frontend on tree-sitter, because they are one language with three
dialects that link into one program. A header and the translation unit that implements it are named
as one module, which is what makes a method declared in one and defined in the other a single node.
`static` and an anonymous namespace are how C narrows a name, an access specifier is how C++ does
it, and both end at the four levels every frontend fills. Resolution is by namespace lookup rather
than by path, so a name the repository states exactly once under some enclosing scope is that name,
and two matches stay unresolved rather than guessing. On the Unicode CUDA library this leaves six
unresolved symbols out of 2,170 edges, and `CU-LAUN0001` finds a real `__shfl_sync` that
Cooperative Groups states more safely.

Each dialect gets the grammar that knows it: `tree-sitter-cuda` for `.cu` and `.cuh`,
`tree-sitter-c` for `.c`, and `tree-sitter-cpp` for everything else. A `.h` goes to the C++ grammar
whatever its project calls itself, because a header cannot say which of the two languages wrote it
and the C++ grammar reads a C header correctly where the C grammar reads a class as an error.

The CUDA grammar is what makes a launch readable. It extends the C++ one with the execution space
qualifiers and the launch bracket, so `__global__` is a node rather than an error the parser
recovered around, `__shared__` is a type qualifier, and `scale<<<grid, block, 0, stream>>>(data)`
arrives as a call carrying its execution configuration. That is the difference between reading a
launch and guessing at one: across 606 CUDA sources in this monorepo it finds 727 launches with no
parse failures, and `CU-LAUN0002` reports the 255 of them that take the default stream and
therefore serialize against every other stream on the device.

### On not writing a C++ parser

The alternatives were checked rather than assumed. `nom`, `pest`, `peg`, and `oak` are parser
generators, so choosing one means writing a C++ grammar, and C++ is the language that cannot be
parsed without a symbol table: the most vexing parse and `a<b>c` both need to know whether a name
is a type before the shape of the statement is decided. `oak` is also a nightly syntax extension
from before the 2018 macro system. `cuda-oxide` and Rust-CUDA parse nothing; the first wraps the
driver API and the second compiles Rust to PTX. `rust-cpp-parser` is a work in progress whose
author writes "don't use it except if you want to contribute". `lang-c` is a real C11 parser with
spans, but it is C only, which leaves the two dialects this repository actually holds. `libclang`
through `clang-sys` is the ground truth and wants a compilation database, include paths, and a
system library, none of which a zero-configuration repository scanner can assume.

That leaves tree-sitter, which was already the right answer. What the research changed is the
grammar per dialect, not the approach.

Archy is a Python producer, so parity with it is a Python statement. There is no oracle to match
for Rust, TypeScript, C, C++, or CUDA. One divergence from Archy is deliberate: a repository, a
directory, and a file are identified as `path:{kind}:{path}` rather than under a language, because
a directory holding Python beside Rust belongs to neither and every frontend that walks into it has
to find the same node already there. Symbols keep `{language}:{kind}:{qualname}`.

Run over the whole `~/projects` monorepo, this reads 11,323 files into 874,468 nodes and 2,766,970
edges in 36 seconds, with Python, C, C++, CUDA, Rust, and TypeScript all in one graph.

- [ ] Demand-driven queries with an invalidation key per fact, so one edited file rebuilds only
      what depends on it
- [ ] Persistent cache under the XDG cache directory, with cache and invalidation counters in stats
- [ ] Tree-sitter frontends for Rust, TypeScript, C, C++, and CUDA behind the same fact types
- [ ] A language-neutral structural baseline every frontend fills, with richer semantics optional

**Done when** a one-file edit rebuilds one file's facts, and the general rules produce findings on
a Rust and a TypeScript source tree without any rule changing.

## Oracles

GE4M is the behavioral oracle for every migrated rule, since it has a working implementation of all
205. Archy is the graph oracle. Ruff, Pylint, Vulture, Lizard, and Symilar are message and metric
oracles for the scopes the kernel claims. An oracle disagreement is a finding about the kernel
until proven otherwise.
