# MCMR against the Python tools, and against the cross-language platforms

## What this document is

An honest account of where MCMR stands beside the tools a Python project actually installs, and
beside the platforms that scan several languages at once. Every number here came from running the
tool on this machine on 2026-07-27, or is labelled as read from documentation. The commands are
written out so anybody can re-run them.

Rule counts are not the headline and should not be. Ruff ships 968 rules and MCMR ships 275, and
that comparison says almost nothing, because the two answer different questions from different
evidence. What follows compares on what each tool can know, and on what a user gets.

## What MCMR is for

MCMR judges a repository against an engineering policy. A rule is a typed Python callable that
receives one fact, returns an occurrence, a count, a percentage, or a closed category, and a
rule-owned acceptance contract decides what that value is worth. The evidence comes from a Rust kernel that walks the
whole tree once, parses six languages into one shared fact vocabulary, builds a resolved import and
call graph across them, and reads the version control log. So the questions MCMR is built for are
the ones a single file cannot answer. Where does this module sit on the main sequence. Which files
keep changing together without importing each other. Which public declaration is read only by the
file that declares it. Which block exists twice. Which rule in the Rust half and which rule in the
Python half are the same rule.

## Where MCMR deliberately does not compete

**Formatting.** MCMR does not format and never will. Black, isort, and the formatter halves of Ruff
and Biome are out of scope, and nothing below compares against them. That is the last sentence on
the subject.

**Type correctness.** MCMR has no type inference at all. It never turns a type error into an
opinion. mypy, pyright, ty, and Pyrefly own that question and MCMR delegates it outright.

**Python local syntax and modernization.** `docs/backlog.md` states the boundary as "never
duplicate" for Ruff, and the account backs it up. Of Ruff's 968 rules MCMR claims 34 and delegates
934.

## How this was measured

Versions, all installed and run here.

| Tool | Version | How it was obtained |
| --- | --- | --- |
| MCMR | 0.0.1, kernel 0.0.1, rustc 1.96.1 | this checkout, `chefe run setup` |
| CPython | 3.14.6 free-threaded, GIL disabled | chefe environment |
| Ruff | 0.15.22 | chefe environment |
| Pylint | 4.0.6, with its own inference library at 4.0.4 | chefe environment |
| mypy | 2.3.0 | chefe environment |
| ty | 0.0.63 | chefe environment |
| Pyrefly | 1.1.1 | chefe environment |
| pyright | 1.1.411 | npm, installed under `/tmp` |
| bandit 1.9.4, vulture 2.16, radon 6.0.1, xenon 0.9.3, pydocstyle 6.3.0, darglint 1.8.1, refurb 2.3.1, perflint 0.8.1, flake8 7.3.0 and plugins, import-linter 2.13, deptry 0.25.1, pip-audit 2.10.1 | as listed | `uv venv` under `/tmp`, Python 3.12.7 |
| wemake-python-styleguide | 1.7.0 | separate `/tmp` venv |
| Semgrep | 1.171.0 | separate `/tmp` venv |
| safety | 3.8.1 | separate `/tmp` venv |
| jscpd | latest npm | `/tmp` npm prefix |
| PMD and CPD | 7.19.0 on OpenJDK 21 | release zip under `/tmp` |
| CodeQL | 2.26.1 bundle | release tarball under `/tmp` |

Nothing was added to `chefe.toml`. Everything that was not already pinned lives under `/tmp`.

Corpora.

| Name | What | Size | Commit |
| --- | --- | --- | --- |
| flask `src/` | the shared head-to-head corpus | 24 files, 9,502 lines | `36e4a824f340fdee7ed50937ba8e7f6bc7d17f81` |
| httpx `httpx/` | a second real library | 23 files | shallow clone, 2026-07-27 |
| sqlalchemy `lib/` | the scale corpus | 255 files, 247,908 lines | `aa1a5575358d3aa14953b04dced02f4763fed2e7` |
| MCMR itself | dogfood | 494 files across five languages | this working tree |
| aizk | a second in-house repository | 490 files | working tree |

flask `src/` is the shared target because it is a real, well-maintained, typed library of a size
every tool here can finish, and because its dependencies can be installed so the type checkers and
Pylint resolve their imports rather than drowning in `import-error`.

## The real dividing line, which is evidence

This is the axis that decides everything else. A tool cannot report what it cannot see.

| Tool | One file | Whole repository | Resolved imports | Inferred types | Reaching definitions | Git history | Installed environment | Runtime |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Ruff | yes | no, by design | no | no | limited, within a scope | no | no | no |
| flake8 and its plugins | yes | no | no | no | limited | no | no | no |
| Pylint | yes | yes, one run over many modules | yes, through its inference library | yes, that library infers | yes | no | yes, it imports what it can | no |
| mypy, pyright, ty, Pyrefly | yes | yes | yes | yes, this is the point | yes | no | yes, required | no |
| bandit | yes | no | no | no | no | no | no | no |
| vulture | yes | yes, one pass over the tree | by name, not resolved | no | no | no | no | no |
| radon, xenon, lizard | yes | metrics only | no | no | no | no | no | no |
| pydocstyle, darglint | yes | no | no | no | no | no | no | no |
| refurb, perflint | yes | no | no | partial, refurb reads annotations | no | no | no | no |
| wemake-python-styleguide | yes | no | no | no | limited | no | no | no |
| import-linter | no | yes | yes, it imports the package | no | no | no | yes, required | no |
| deptry | yes | yes | names only | no | no | no | yes, reads the manifest | no |
| pip-audit, safety | no | no | no | no | no | no | yes, this is the input | no |
| Semgrep | yes | yes, with interfile mode in the paid tier | partial | partial | yes, within a function | no | no | no |
| CodeQL | yes | yes | yes | yes | yes, full dataflow and taint | no | partial | no |
| SonarQube | yes | yes | yes | yes for the type-aware rules | yes | yes, for new-code and churn | no | via coverage import |
| PMD and CPD | tokens only | CPD only | no | no | no | no | no | no |
| jscpd | tokens only | yes | no | no | no | no | no | no |
| **MCMR** | yes | yes | yes, a resolved cross-language graph | **no** | **no** | yes | partly, it reads the manifest | **no**, it reads a records directory instead |

Three cells decide most of what follows. MCMR has a resolved graph and git history that Ruff and
flake8 do not have. MCMR has no type inference where Pylint and the four type checkers do. MCMR has
no dataflow where CodeQL and Semgrep do.

## MCMR's own inventory, measured

```
chefe run -- python -m mcmr.cli coverage --tool pylint
chefe run -- python -m mcmr.cli coverage --tool ruff
chefe run -- python -m mcmr.cli coverage --tool clippy
```

| | Rules | Lanes | Scopes | Fixes |
| --- | --- | --- | --- | --- |
| MCMR catalog | 275 across 63 families | 230 deterministic, 45 contextual | 151 general, 112 Python, 5 Rust, 4 TypeScript, 3 CUDA | 31 fixes |

Result shapes are 152 counts, 68 categories, 37 occurrences, 22 percentages, over 85 distinct fact
families.

Derived accounts, read out of the rule docstrings rather than maintained beside them.

| Upstream | Rules | native | delegated | adapted | inapplicable | unavailable |
| --- | --- | --- | --- | --- | --- | --- |
| Pylint 4.0.6 | 389 | 22 | 269 | 6 | 19 | 73 |
| Ruff 0.15.22 | 968 | 34 | 934 | 0 | 0 | 0 |
| Clippy | 809 | 10 | 799 | 0 | 0 | 0 |
| ESLint | 292 | 4 | 1 | 0 | 93 | 194 |
| typescript-eslint | 134 | 3 | 0 | 1 | 8 | 122 |
| clang-tidy | 604 | 3 | 0 | 0 | 78 | 523 |
| cppcheck | 342 | 0 | 0 | 0 | 5 | 337 |

That the account is derived from the rules rather than hand-written beside them is a real design
win, and no other tool in this document publishes an equivalent. It is also why the next section
matters, because an account of what a rule claims is not an account of what a rule does.

### What the earlier corpus audit exposed

Before the provider and finding repairs, four real corpora, MCMR itself, flask, httpx, and aizk,
ran under the then-current default policy. For every
deterministic rule the audit records whether it received a fact at all, and whether it produced any
finding or failure.

| Deterministic rules, 214 total | Count |
| --- | --- |
| fired on at least one corpus | 111 |
| received evidence somewhere and fired nowhere | 70 |
| never received a fact on any corpus | 33 |

Some of the 70 were correct silence. `PY-TORC0001` has nothing to say about a repository with no
torch in it, and `TS-MODU0001` has nothing to say about Python. Others exposed provider defects.
Clone groups now carry every participating file, the override family receives resolved members,
and dependency cycles are derived from the repository graph rather than one file at a time.

Of the 33 that never received a fact in that measurement, ten were the data-asset family, three
were CUDA rules on Python corpora, and most of the rest had no source or provider implementation.
MCMR no longer accepts hand-written retained evidence as a substitute for a provider.

The 65 contextual rules have executable backends and precise findings. A 2026-07-28 Sol sweep ran
the then-current 63 with no backend failure, consuming 1,018,795 input tokens and 9,472 output
tokens in 71.7 seconds. Its sparse evidence proved the runtime and provenance paths but not
semantic quality. `mcmr contextual-experiment` compares an explicitly supplied complete reviewed
corpus through GLiNER2 base, Luna none through high, and Terra medium, with Sol medium optional.
The repository does not yet bundle that corpus, so this remains an experiment contract rather than
a completed semantic gate.

## Ruff

Ruff is the tool MCMR is most often measured against and the one it is least in competition with.

```
ruff rule --all --output-format json | jq length            # 968
ruff check --no-cache --isolated --select ALL src           # on flask
```

968 rules, drawn from 59 upstream linters, of which 150 are preview. 251 rules always have a fix,
223 sometimes have one, 494 have none. On flask `src/` the default rule set reports 0 findings, the
whole `ALL` selection reports 1,214 findings from 87 distinct rules in 14 ms, and `ALL` with preview
reports 1,493.

What Ruff can know is one file at a time, plus a per-file semantic model good enough for scope and
binding resolution. It has no cross-file graph, no inferred types, and no history. It does not need
them for what it answers.

**Where Ruff is better than MCMR.**

- Speed, by two orders of magnitude. On sqlalchemy `lib/`, 255 files and 247,908 lines, Ruff with
  every rule enabled takes 0.11 s and MCMR takes 14.04 s.
- Breadth of local checks. 968 rules covering pyupgrade, pyflakes, pycodestyle, pep8-naming,
  flake8-pyi, pandas-vet, NumPy, Airflow, FastAPI, and Django is a surface MCMR will never rebuild
  and correctly does not try to.
- Fixes that are actually applied. `ruff check --fix` edits the file. MCMR renders a `[*]` or
  `[?]` marker and has no command that applies anything.
- Safety modelling on those fixes, split into always-available, sometimes-available, and display
  only, with `--unsafe-fixes` as an explicit opt in.
- Suppression. `# noqa: F401` works, and `RUF100` reports the suppressions that stopped being
  needed. MCMR has no suppression mechanism at all.
- Configuration. Per-directory `[tool.ruff]` sections, per-file ignores, `respect-gitignore` on by
  default, and per-rule settings a project states in its own manifest.
- Correctness on the one rule they share head to head. See the unused-import section below.

**Where MCMR answers something Ruff cannot.** Cross-module import cycles and coupling, duplication
across files, git hotspots and co-change, cross-language seams, and the same rule answering for
Rust and CUDA as well as Python. Cognitive complexity is the clean example. Ruff ships mccabe
`C901` and nothing else, while `ALL-FUNC0008` scores nesting-annotated control increments the
provider supplies, so one definition serves six languages.

## Pylint

```
pylint --rcfile=/dev/null --score=n --persistent=n src/flask
```

389 messages across 31 checkers, verified by reading `PyLinter.msgs_store` rather than a remembered
figure. 130 errors, 134 warnings, 61 refactors, 50 conventions, 9 informational, 5 fatal. On flask
`src/`, with the dependencies importable, Pylint reports 231 messages in 2.09 s.

Pylint's advantage over everything else in the Python-only list is its inference library. It infers
types, follows
assignments, resolves inheritance chains, and imports what it can find, and 52 of the 73 messages
MCMR records as unavailable are unavailable precisely because they need that inference.

**Where Pylint is better than MCMR.**

- Type inference, which is the whole reason it can answer `no-member`, `not-callable`,
  `unsupported-binary-operation`, and fifty more.
- Cyclic import detection that works. On flask `src/` Pylint reports 5 `cyclic-import` messages
  and MCMR reports 0. This is examined below and it is a defect in MCMR.
- Inline and block suppression with `# pylint: disable=`, plus `useless-suppression` to find the
  disables that expired.
- A configuration file the project owns, with per-message enable and disable, per-checker options,
  and a plugin API that has produced a real ecosystem.
- Maturity of the messages themselves. Every one has a documentation page, a symbolic name, and
  years of false-positive reports behind it.

**Where MCMR is ahead.** MCMR's 22 native claims against Pylint are mostly the graph-shaped ones,
the override family, class surface size, ancestor depth, and duplication. Two of those are verified
against Pylint by a Hypothesis oracle in `tests/test_upstream_oracle.py`, and the K4 work records
exact agreement on nine override messages. What MCMR adds beside them is the history and coupling
families Pylint has no equivalent for.

## flake8 and the plugin ecosystem

```
flake8 --max-line-length=120 src        # with the plugins listed below installed
```

1,014 findings on flask `src/`, in 1.23 s, from a stack of flake8 7.3.0 plus bugbear,
comprehensions, simplify, bandit, return, boolean-trap, async, todos, print, eradicate, annotations,
and cognitive-complexity. The breakdown by prefix is 541 darglint, 275 annotations, 70 boolean trap,
39 pyflakes, 28 cognitive complexity, 24 pycodestyle, 13 return, 12 bandit, 9 simplify, 2 bugbear,
1 mccabe.

Maintenance status, read from PyPI and the GitHub API on 2026-07-27, because recommending a dead
plugin is worse than not naming it.

| Plugin | Latest release | State |
| --- | --- | --- |
| flake8-bugbear 25.11.29 | 2025-11-29 | alive |
| flake8-comprehensions 3.17.0 | 2025-09-09 | alive |
| flake8-simplify 0.30.0 | 2026-01-01 | alive |
| flake8-async 27.7.1 | 2026-07-16 | alive, actively developed |
| flake8-annotations 3.2.0 | 2025-10-09 | alive |
| eradicate 3.0.1 | 2025-10-27 | alive |
| flake8-boolean-trap 1.0.1 | 2023-07-17 | dormant, repo still touched |
| flake8-eradicate 1.5.0 | 2023-05-31 | dormant |
| flake8-return 1.2.0 | 2022-10-28 | dormant |
| flake8-bandit 4.1.1 | 2022-08-29 | dormant |
| flake8-print 5.0.0 | 2022-04-30 | dormant |
| flake8-todos 0.3.1 | 2024-02-09 | dormant |
| flake8-cognitive-complexity 0.1.0 | 2020-08-01 | effectively abandoned, last repo push 2021-02-24 |

Every one of those plugins is reimplemented in Ruff, usually under the same code, so the honest
recommendation for a new project is Ruff rather than the flake8 stack. The plugins are named here
because MCMR's own `References` sections cite them and because `docs/kernel.md` identifies exactly
this seam, bugbear, bandit, boolean-trap, tryceratops, return, todos, print, and blind-except, as
the set of Ruff ideas that are not about Python at all and can be generalized. `ALL-PARA0003` is the
first of them.

Two meta-linters are worth naming and skipping. **prospector** 1.19.1 is alive and bundles Pylint,
pycodestyle, mccabe, dodgy, and others behind one profile. **pylama** 8.4.1 last released in 2022.
**dodgy** last released in 2019 and is only reachable through prospector. None of the three add a
kind of evidence, they aggregate tools already covered here.

## The type checkers, and pyflakes

MCMR does not compete here, so this section is short and exists to make the delegation concrete.

Same 24 files, same installed dependencies, wall time best of three.

| Tool | Findings | Time |
| --- | --- | --- |
| mypy 2.3.0, reading flask's own strict `[tool.mypy]` | 1 error | 1,638 ms |
| pyright 1.1.411, basic mode | 4 errors | 1,186 ms |
| Pyrefly 1.1.1 | 31 errors, 60 suppressed, 10 warnings hidden | 130 ms |
| ty 0.0.63 | 98 diagnostics | 76 ms |

Two honest readings. The two Rust checkers are ten to twenty times faster and are not yet calibrated
to the same answer, which is what a version number below 1.0 for ty and a very recent 1.0 for
Pyrefly should lead a reader to expect. And a type checker without the installed environment is
useless. Before the dependencies were installed, mypy reported 130 errors of which 49 were
`import-not-found` and ty reported 125 of which 56 were `unresolved-import`.

**pyflakes** 3.4.0 is alive and is the engine inside flake8 for the `F` codes. **Pylance** is the
Microsoft closed-source VS Code extension wrapping pyright, so it is not runnable here as a CLI and
adds no distinct evidence class over pyright.

**Where all four are better than MCMR.** They know what a name means. MCMR has no inference, which
is why `AttributeAccessFact`, `CallFact.calls[].resolved_type`, and thirteen other fields sit in the
frozen-field ledger as never written. It is also the single reason the unused-import rule below is
wrong.

## bandit

```
bandit -r -q src
```

12 issues on flask `src/` in 253 ms, 1 high, 3 medium, 8 low, across `assert_used`, `exec_used`,
`hardcoded_password_string`, `try_except_pass`, `blacklist`, `hashlib`, and
`markupsafe_markup_xss`. bandit 1.9.4 released 2026-02-25 and is alive.

MCMR's security family is 5 deterministic rules plus 2 model rules. On the same corpus MCMR reports
2 findings, `ALL-SECU0002` for the SHA-1 call in `sessions.py` and `ALL-SECU0004` for one hardcoded
credential. bandit and Semgrep both find the SHA-1 too, so the three agree where they overlap.

**Where bandit is better.** Roughly seventy plugin checks against MCMR's five, a severity and
confidence model MCMR has no equivalent of, and a baseline mode. Ruff's flake8-bandit port is 73
rules and is faster than both.

**Where MCMR differs usefully.** MCMR generalizes S105, S106, S107, S110, S112, S311, S324, S602,
S604, and S605 into general rules that also answer for Rust and C++, which no Python security tool
does.

## vulture

```
vulture src                       # 76 items
vulture --min-confidence 100 src  # 7 items
```

76 items on flask `src/` in 85 ms, of which 69 carry 60 percent confidence and 7 carry 100 percent.
The 60 percent tier is dominated by public library methods whose callers live outside the
repository, which is the structural false positive of dead-code detection on a library.

MCMR asks a different question with `SymbolReachFact`. `ALL-REAC0001` counts public declarations
nothing in the repository reaches, and `ALL-REAC0002` names a public declaration read only inside
its own file, which is an over-exported API rather than dead code. On flask `src/` that is 9 and 23
findings. It has the same structural problem, flagging `FlaskGroup` and `NoAppException`, which are
real public API.

**Where vulture is better.** It points at the exact line. MCMR's reach findings point at the file,
`flask/cli.py:1:1`, and carry a per-file count.

**Where MCMR is better.** The graph behind it resolves imports and re-export chains, and the change
that made annotations count as edges took unreached public declarations in MCMR's own source from
177 to 76, which is a class of false positive vulture cannot remove by name matching.

## radon, xenon, lizard, cohesion

```
radon cc -s -n C src     # 10 blocks at C or worse
xenon --max-absolute C --max-modules B --max-average A src
```

radon 6.0.1 last released 2023-03-26 and xenon 0.9.3 on 2024-10-21, both still receiving repository
activity in late 2024 and neither archived. On flask `src/` radon lists 10 blocks at rank C or
worse, the worst being `Blueprint.register` at 23, and xenon exits nonzero naming exactly that block.
lizard 1.23.0 released 2026-06-02 and is alive, and `docs/kernel.md` already names it as a metric
oracle. cohesion 1.2.0 measures class cohesion and last released 2024-12-09.

MCMR's answer is `ALL-FUNC0008` cognitive complexity at 7 findings, `ALL-FUNC0007` explicit branches
at 4, `ALL-FUNC0001` direct statements at 19, and `ALL-FUNC0009` nesting depth. The measure is
cognitive complexity rather than cyclomatic, so the two do not line up rank for rank, and MCMR's
version is language neutral where radon parses Python only.

**Where radon and xenon are better.** They report the maintainability index and the raw metrics, they
rank blocks A through F which is easier to act on than a bare number, and xenon is a one-line CI gate.
MCMR's typed acceptance contracts do the gating job without another CLI flag. Each rule owns its
default, and a project can replace that contract with a validated rule-level override.

## pydocstyle and darglint

Both are archived on GitHub. pydocstyle 6.3.0 released 2023-01-17 with the last repository push on
2023-11-03. darglint 1.8.1 released 2021-10-18 with the last push on 2022-12-08. They still run, and
on flask `src/` pydocstyle reports 563 violations and darglint reports 560, so a project that
depends on them is not broken. It is unmaintained. Ruff's pydocstyle port is 48 rules and its
pydoclint port is 7, and that is where new work should go.

MCMR's `PY-DOCU0001` is a different animal and the honest comparison is unflattering in one specific
way. It reports 233 findings on flask `src/`, which is 51 percent of everything MCMR says about that
repository, and every one of them enforces a house docstring style flask never agreed to. Two
examples from the run.

```
the docstring of `get_db` opens with 64 characters that do not read as one finished sentence
the docstring of `open_resource` carries a heading or a label where this project writes plain lines
```

Those are real observations of a real preference. Reporting them by default on a repository that has
not opted in is what makes MCMR's first run on a foreign project read as noise, and there is no way
to turn the rule off short of `--select`, which selects rather than deselects.

## refurb and perflint

```
refurb src        # 19 findings, 2,382 ms
```

refurb 2.3.1 released 2026-04-03 and is alive. It reads annotations, so it knows a little more than
a purely syntactic checker, and its findings on flask `src/` are led by FURB126, FURB123, FURB146,
FURB107, and FURB104. Ruff ports 36 refurb rules.

perflint 0.8.1 released 2024-01-10 with the last repository push on 2024-02-19, so it is dormant
rather than dead. Ruff ports 6 of its rules under `PERF`, and `PERF401` fires once on flask `src/`.

MCMR has a performance family but it reads `PerformanceDecisionFact`, which is an evidence-store
family a project writes by hand, so on source alone MCMR says nothing here. Both tools win outright.

## wemake-python-styleguide

```
flake8 --select=WPS --max-line-length=120 src   # 774 findings, 462 ms
```

1.7.0 released 2026-07-26, the most actively maintained thing in this section. It is the closest
philosophical relative MCMR has, because it is explicitly an opinionated house style rather than a
correctness checker, and because it judges shapes such as too many module members, overuse of a
literal, and jones complexity that no other Python linter judges.

**Where it is better than MCMR.** 774 findings against MCMR's 456 on the same tree, every one at an
exact line, with a documented violation page and a stable numeric code. It plugs into flake8 so the
whole `noqa` and per-file-ignore machinery comes for free.

**Where MCMR is better.** MCMR's opinions are graded across three profiles and stated as intervals a
rule reports a value against, so a project reads `9, allowed <= 8` rather than a binary violation.
And MCMR's opinions travel to Rust, TypeScript, and CUDA. wemake is Python only and always will be.

## import-linter

```
lint-imports --config /tmp/mcmr-cmp/importlinter.ini
```

2.13 released 2026-07-03 and is alive. It found real layering violations on flask, printing the
import chain that caused each one, which is excellent output.

```
flask.ctx is not allowed to import flask.globals
- flask.ctx -> flask.wrappers (l.23)
  flask.wrappers -> flask.globals (l.11)
```

Two costs. It imports the package, so the environment has to be complete and `PYTHONPATH` has to be
right, and it needs the project to write a contract. `docs/kernel.md` argues that a layering contract
in a config file rots, because somebody widens it every time a legitimate edge fails, and derives
`ModuleCouplingFact` every run instead. `ALL-ARCH0003` reports an import pointing at a less stable
module and found 6 on flask `src/` with no contract written at all, and `ALL-ARCH0004` reported 4
modules in the zone of pain.

That is a genuine architectural advantage and it is the clearest single case where MCMR's design
choice beats an established tool.

**Where import-linter is still better.** A project that wants `domain` never to import `infra` can
say exactly that, and MCMR has no way to express it. Instability is a proxy for layering, not a
statement of intent. And import-linter names the chain, where `ALL-ARCH0003` names one module.

## deptry

```
deptry .        # 53 issues on the flask repository
```

0.25.1 released 2026-03-18 and is alive. It reads the manifest and the imports, and reports missing
dependencies, unused dependencies, dev dependencies used in production code, and transitive
dependencies relied on directly. On flask it correctly named `python-dotenv` as declared and unused
and `cryptography` as a dev dependency imported by `src/flask/cli.py`.

MCMR reads `DependencyFact` and `DependencyCandidateFact` and has 8 rules over them, but this
comparison is a loss. deptry's four categories are precisely the questions a dependency manifest
raises, and MCMR has nothing that reports them with that precision.

## pip-audit and safety

```
pip-audit --local        # No known vulnerabilities found
safety scan              # refuses to run without a login
```

pip-audit 2.10.1 released 2026-06-10, alive, runs with no account, queries PyPI and OSV, and is the
one to recommend. safety 3.8.1 released 2026-05-29 is alive but its CLI now demands registration
before it will scan, which is a real adoption cost worth stating plainly.

MCMR does not do vulnerability scanning and should not. This is a database question rather than a
code question.

## The cross-language platforms

### CodeQL

```
codeql database create db --language=python --source-root=src   #  2.24 s
codeql database analyze db python-security-and-quality.qls      # 15.99 s
```

174 queries in the security-and-quality suite, 45 in the default code-scanning suite, 52 in
security-extended. 34 results on flask `src/`, led by 24 `py/ineffectual-statement`, then
`py/missing-call-to-init` twice, `py/import-and-import-from` twice, and one each of `py/empty-except`,
`py/missing-equals`, `py/unused-global-variable`, `py/import-own-module`, `py/unused-import`, and
`py/unreachable-statement`.

**Where CodeQL is better than MCMR, decisively.** It has interprocedural dataflow and taint tracking.
That is a whole kind of judgment MCMR cannot make and has no plan to make. A source-to-sink query
crossing four functions and two modules is routine for CodeQL and impossible for a fact-and-rule
engine with no value flow. It also covers ten languages with per-language libraries far deeper than
MCMR's shared vocabulary, and QL is a real query language with a compiler and an optimizer.

Notice that CodeQL found 2 `py/missing-call-to-init` where Pylint found 0 `super-init-not-called` and
MCMR's `ALL-OVER0006` found 0. Three tools claiming the same concern, two silent.

**Where MCMR is different rather than worse.** CodeQL builds a database and runs a suite, and its
unit of thought is a query over a relational model. MCMR's unit is a typed callable with an
acceptance policy attached, so a project can override one rule's contract without rewriting its
query. And CodeQL has nothing about git history or duplication.

### Semgrep

```
semgrep --config=p/python src     # 151 rules,  1 finding
semgrep --config=p/security-audit src  #  79 rules,  3 findings
semgrep --config=p/default src    # 290 rules,  4 findings
semgrep --config=r/python src     # 372 rules, 15 findings
```

1.171.0 released 2026-07-22 and is the most active thing in this document. 1,449 ms for the
`p/python` pack on flask `src/`.

**Where Semgrep is better than MCMR, decisively.** The pattern language. A rule is a piece of code
with holes in it, so a person writes and tests a new rule in minutes rather than adding a fact
family to a Rust kernel and a typed callable to a Python catalog. It has autofix through `fix:`, it
has `# nosemgrep`, it has a public registry with thousands of community rules, and it already covers
thirty-plus languages with one syntax.

This matters specifically for MCMR's own backlog. Items 10 through 14 of `docs/backlog.md`,
hand-rolled registries, task-runner bypass, prose punctuation policy, defensive import guards, and
broad exception handlers outside an entry point, are all pattern rules. Each would be a five-line
Semgrep rule and each is currently a kernel change plus a catalog change in MCMR.

**Where MCMR is better.** Semgrep's free tier is per-file. Cross-file analysis is a paid feature. So
the questions MCMR is built for, coupling, cycles, reach, duplication across files, and history, are
outside what free Semgrep can see. And Semgrep has no notion of a measured value judged against a
typed acceptance contract, only match or no match.

### SonarQube and SonarSource

Not run here. SonarQube Community requires a server, a database, and a scanner run, and standing one
up was not a defensible use of this session. Claims below are from documentation at
<https://rules.sonarsource.com/python/> and <https://docs.sonarsource.com/>.

SonarSource publishes several hundred Python rules across bug, vulnerability, code smell, and
security hotspot categories, plus roughly thirty languages under one engine, a quality gate model, a
new-code-period concept that judges only what changed, and a duplication measure. Its cognitive
complexity paper is the source `ALL-FUNC0008` implements, and MCMR's upstream registry already
carries a `SonarSource` profile with the `S\d+` code pattern.

**Where Sonar is better.** The new-code gate and historical measures add a UI, issue assignment,
and a decade of false-positive tuning that a stateless command does not attempt. The taint analysis
in the commercial tiers is real dataflow. The rule descriptions also explain the risk, fix, and
exceptions in a mature user interface.

**Where MCMR is different.** MCMR is a CLI with no server, and the whole judgment is derivable from
the checkout.

### PMD and CPD

```
pmd cpd --minimum-tokens 50 --language python --dir src   # 8 duplications, 357 ms
```

PMD 7.19.0. Worth being precise about what it covers, because it is often listed as a Python tool
and it is not. PMD ships `pmd-python`, but only as a CPD tokenizer. There is no
`category/python/*.xml` ruleset, and asking for one fails with `Cannot resolve rule/ruleset
reference`. So for Python, PMD is a copy-paste detector and nothing else.

### jscpd

```
jscpd --min-tokens 50 --format python src
```

22 clones, 3.43 percent duplicated lines, 4.80 percent duplicated tokens, in 66 ms. It covers 150-odd
formats through one tokenizer and reports a repository-level share.

MCMR's `ALL-DUPL0003` reports 25 groups and 36 findings on the same tree, and `ALL-DUPL0004` states
the share one group at a time rather than for the whole run. The messages are better than either
competitor.

```
flask/sansio/blueprints.py:441:1: ALL-DUPL0003 these 50 lines repeat what
`flask/sansio/app.py` already states at lines 711 to 769 (4, allowed <= 0)
```

`docs/backlog.md` states the boundary as "consume locations, decide shared knowledge separately", and
in practice MCMR reimplemented the detector rather than consuming one. The reimplementation is
competitive, matching Symilar exactly on locations and share per the K4 record, and normalizing
identifiers so a renamed copy is still a copy.

### DeepSource, Codacy, Qodana, Code Climate

None were run. All four are hosted platforms requiring an account and a repository connection, and
claims here are from documentation.

- **DeepSource**, <https://deepsource.com/>. Multi-language, Python analyzer plus a secrets analyzer,
  autofix pull requests, and a code-health metric. Its distinguishing feature over a linter is the
  hosted baseline, so existing issues do not block a pull request.
- **Codacy**, <https://www.codacy.com/>. Aggregates open-source engines rather than owning an
  analysis. For Python that means Pylint, bandit, prospector, and others behind one dashboard, plus
  duplication through its own detector and coverage import.
- **Qodana**, <https://www.jetbrains.com/qodana/>. Runs the IntelliJ and PyCharm inspections
  headlessly, which is a real evidence advantage, because those inspections use the same resolved
  PSI and type inference the IDE uses. That puts Qodana in the same evidence class as Pylint and the
  type checkers rather than the linter class.
- **Code Climate**, <https://codeclimate.com/>. The maintainability engine plus a plugin protocol
  wrapping existing linters. Its churn-versus-complexity view is the same idea `ALL-HIST0001`
  implements.

The shared point is that all four sell baselines, trends, gates, and team reports. MCMR deliberately
stays a stateless local check, so those product features remain outside its scope.

## One corpus, side by side

flask `src/`, 24 files, 9,502 lines, every tool with the flask dependencies importable. MCMR used
the then-current default policy.

| Concern | Ruff `--select ALL` | Pylint | MCMR |
| --- | --- | --- | --- |
| Boolean trap | `FBT001` 42, `FBT002` 32, each naming the parameter | none | `ALL-PARA0003` 26 sites summing to 39 parameters, `ALL-PARA0004` 1 site of 4 |
| Superfluous else after a jump | `RET505` 7, `RET506` 2 | `no-else-return` 3, `no-else-raise` 2, `no-else-continue` 1 | `ALL-CONT0001` 9 |
| Private member access from outside | `SLF001` 16, at the access | `protected-access` 16, at the access | `ALL-ENCA0001` 6 file-level sites summing to 17 |
| Too many parameters | `PLR0913` 6 | `too-many-arguments` 4, `too-many-positional-arguments` 4 | `ALL-FUNC0010` 6, naming every required parameter |
| Too many branches | `PLR0912` 4 | `too-many-branches` 3 | `ALL-FUNC0007` 4 |
| Complexity | `C901` 5, cyclomatic | none by default | `ALL-FUNC0008` 7, cognitive |
| Commented-out code | `ERA001` 4 | none | `ALL-COMM0002` 2 sites, 3 blocks |
| Weak hash | `S324` 1 | none | `ALL-SECU0002` 1 |
| try/except pass | `S110` 1 | none | `ALL-ERRO0001` 4 |
| Raise inside try | `TRY301` 2 | none | `ALL-ERRO0004` 5 |
| Blanket suppression | `PGH003` 21, `PGH004` 1 | none | `ALL-WAIV0001` 17 |
| Duplicate code | none | `duplicate-code` 1 | `ALL-DUPL0003` 25 groups, 36 findings |
| Cyclic imports | none | `cyclic-import` 5 | `ALL-ARCH0002` **0**, and this is wrong |
| Unused import | `F401` **0** | `unused-import` 3 | `PY-IMPO0003` **31**, and most are wrong |
| Layering | none | none | `ALL-ARCH0003` 6, `ALL-ARCH0004` 4 |
| Git hotspots | none | none | `ALL-HIST0001` 2, `ALL-HIST0002` 12, `ALL-HIST0003` 3 |
| Over-exported API | none | none | `ALL-REAC0002` 23 |
| Docstring house style | `D` rules 300-odd | `missing-*-docstring` 39 | `PY-DOCU0001` 233 |
| **Total** | 1,214 findings, 87 rules | 231 messages, 40 symbols | 456 findings, 54 rules, 567 failures |

The bottom four rows are what MCMR is for. The two bold rows are where it is broken.

## Two defects found while writing this

Both are reported rather than fixed, per the terms of this exercise. Both are reproducible.

### The unused-import rule has three false-positive classes

`PY-IMPO0003` claims `Generalizes Pylint W0611 unused-import`, and `docs/kernel.md` records that the
stream "agrees with Ruff exactly" on MCMR's own source. It does not agree on other people's source.

On flask `src/`, Ruff reports 0 `F401` and MCMR reports 31. On httpx, Ruff reports 0 and MCMR reports
50. Minimal reproduction, written to `/tmp` and run with `mcmr check --select unused_import`.

```python
from decimal import Decimal
from fractions import Fraction
from numbers import Number
from pathlib import Path

def one(value: object) -> str:
    if isinstance(value, Number):     # Number counts as a use, correct
        return "n"
    return "x"

def two(value: object) -> str:
    if value is None:
        return "none"
    elif isinstance(value, Decimal):  # Decimal is reported unused, wrong
        return "d"
    return "x"

def three(value: object) -> str:
    if value is None:
        return "none"
    else:
        return str(Fraction(1))       # Fraction counts as a use, correct

def four(value: object) -> str:
    try:
        return str(value)
    except Path as error:             # Path is reported unused, wrong
        return str(error)
```

MCMR reports `Decimal` and `Path`. Ruff reports nothing. So a name used only in an `elif` test and a
name used only as an exception handler type are both invisible to the reference resolver.

The third class is `from __future__ import annotations`, which is reported unused in every file that
carries it, 19 of the 50 findings on httpx and 22 of the 31 on flask. flask declares
`requires-python = ">=3.10"`, where that import is still load-bearing.

The fourth, and the most alarming, is a wildcard re-export. On httpx, MCMR reports all eleven
`from ._api import *` lines in `httpx/__init__.py` and all five in `httpx/_transports/__init__.py` as
unused imports.

Every one of these findings carries a marker saying an `Edit` repair is attached. Nothing in MCMR
applies edits today, so no harm has been done, but the fix that is written would delete a package's
entire public API and would delete a `__future__` directive from a file that needs it. The marker
read `[*]`, which promises the edit is safe to apply unattended, until two things changed after
this was measured. The repair is now declared as wanting review, and the renderer now reads that
declaration rather than the mere existence of an edit, so these print `[?]`.

The reason the self-scan never caught this is worth recording. MCMR's own source has one
`__future__` import in the whole tree, no wildcard re-exports, and a house style that rarely writes
`elif`. An oracle validated only against the author's own code cannot see the shapes the author does
not write.

### The import-cycle rule can never report a cycle

`ALL-ARCH0002` claims `Generalizes Pylint R0401 cyclic-import`, `mcmr coverage --tool pylint` records
it as native, and `SYSTEM.md` uses it as the worked example of a rule that receives directed import
edges and computes strongly connected components.

On flask `src/` it reports 0. Pylint reports 5 `cyclic-import`. An independent computation over the
same tree with `ast` and `networkx` finds one strongly connected component of 11 modules with
`TYPE_CHECKING` imports excluded, and one of 20 with them included.

And `mcmr matrix` over the same tree prints the cycle.

```
Cycles (1)
  flask flask.app flask.blueprints flask.cli flask.debughelpers flask.templating
  flask.testing flask.wrappers
```

The graph is right. The fact is not. `DependencyComponentFact` is built one per file, and dumping it
shows that `flask/app.py` carries only external targets, `werkzeug.routing`, `click`, `collections.abc`,
with no internal relative imports at all, while `flask/__init__.py` carries an empty edge list. The
edge sources are spelled `flask.app.py` and the targets are spelled `collections.abc`, so the two
namespaces do not even meet. A strongly connected component over one file's external imports is
always zero.

This is exactly the defect class `docs/kernel.md` sections K2e and K2f were written to close, and
`tests/test_fact_variation.py` cannot catch it, because `import_edges` does vary across facts. It is
just varying over the wrong edges.

## Configuration, and what a project has to state

| Tool | Config file | Per-rule enable and disable | Inline suppression | Respects `.gitignore` | Needs a contract to be useful |
| --- | --- | --- | --- | --- | --- |
| Ruff | `[tool.ruff]`, per-directory, per-file ignores | yes, by code and prefix | `# noqa`, plus `RUF100` for stale ones | yes, by default | no |
| Pylint | `.pylintrc` or `[tool.pylint]` | yes, by symbol and category | `# pylint: disable=` | via `ignore-paths` | no |
| flake8 | `setup.cfg`, `tox.ini` | yes | `# noqa` | via `extend-exclude` | no |
| mypy, pyright, ty, Pyrefly | yes, all four | yes | `# type: ignore`, `# pyright: ignore`, and equivalents | yes | no |
| bandit | `.bandit`, `[tool.bandit]` | yes | `# nosec` | via `exclude_dirs` | no |
| vulture | whitelist file | by whitelist | no | no | a whitelist, in practice |
| Semgrep | `.semgrep.yml`, registry packs | yes | `# nosemgrep` | yes | rules, if you write your own |
| import-linter | `.importlinter` | contracts are the config | no | not applicable | **yes**, it does nothing without one |
| CodeQL | query suites | by suite and query | `// codeql[...]` | not applicable | no, suites ship |
| **MCMR** | `[tool.mcmr]` in `pyproject.toml` | yes, by rule identifier | no | yes | no |

MCMR has no selectable built-in policy mode. `[tool.mcmr]` can select or disable rules, override an
individual rule policy or setting, and configure discovery and execution lanes. The CLI can narrow
the rule selection and source suffixes for one run. Discovery follows Git ignore files rather than
a hardcoded vendored list.

The design argument for this is good and it is stated well in `docs/kernel.md`. A layering contract
in a config file rots, and deriving the judgment every run keeps it honest. The argument does not
extend to having no configuration at all. `PY-DOCU0001` producing 51 percent of the findings on a
repository that never adopted the house docstring style is the cost, and today the only remedy is to
not run MCMR.

MCMR does read `# noqa`, `# type: ignore`, `# pyrefly: ignore`, and `# ty: ignore`, but only as
evidence for `ALL-WAIV0001`, which counts suppressions that lack a reason, a date, or a bounded
scope. That is a genuinely good idea nobody else has. It is not a suppression mechanism.

## Fixes

| Tool | Fixes | Safety modelled | Applied by the tool |
| --- | --- | --- | --- |
| Ruff | 251 always, 223 sometimes, 494 none | yes, safe versus unsafe, `--unsafe-fixes` opts in | yes, `--fix` |
| Pylint | none | not applicable | no |
| Semgrep | per-rule `fix:` | no | yes, `--autofix` |
| CodeQL | suggestions in some queries | no | no |
| DeepSource, Codacy, Qodana | autofix pull requests | varies | yes, hosted |
| **MCMR** | **23 fixes on 22 rules** | **yes, safe versus review** | **no** |

MCMR's fix contract is the best-designed one in this list and it is the least delivered. A fix
returns typed rewrites over resolved nodes rather than a text patch, five operations expose the spans
they touch so the engine detects conflicts without knowing any rule, and `docs/autofix.md` specifies
import management, atomic application, reparse, re-running the rule before an edit is kept, iteration
to a fixpoint, and `--fix` applying only safe plans.

The application half still does not exist. There is no `--fix` flag on any command and no rewrite
renderer in the kernel. The `[*]` and `[?]` markers in the output announce a repair that no command
can perform.

## Output quality

The concise register is good and reads like Ruff's.

```
src/flask/app.py:310:5: ALL-FUNC0010 `__init__` cannot be called without `import_name`,
`static_url_path`, `static_folder`, `static_host`, `host_matching`, `subdomain_matching`,
`template_folder`, `instance_path`, `instance_relative_config`, `root_path`, which is
10 parameters of the 11 it declares (10, allowed <= 5)
```

That names the callable, lists the parameters, states the value, and states the bar. Ruff's
`PLR0913` says `Too many arguments in function definition (10 > 5)` and nothing else. On its best
rules MCMR's messages are the best in this document.

That output gap is closed. Every one of the 279 rules now returns a reporting shape, and a catalog
guard fails if any rule falls back to a scalar-only answer. The fixture suite checks exact messages,
locations, measurements, evidence, provenance, and repairs across every result shape. A rule can
still return no finding when its evidence does not qualify, which is silence rather than a generic
summary pretending to identify a defect.

```
flask/app.py:1:1: ALL-ENCA0001 Count nonpublic members accessed outside their declaring type. (5, allowed <= 0)
```

That is a whole-file span, a count, and an imperative sentence describing the rule rather than the
code. A reader cannot act on it and neither can an agent. Pylint's `protected-access` names the
attribute at the exact line, sixteen times.

Other gaps worth naming.

- No SARIF output. `mcmr check --format json` does provide the complete machine-readable diagnostic
  stream, while SARIF integration remains open.
- Two whole-repository history rules report at an empty path, printing `:1:1: ALL-HIST0002` with a
  count and the rule summary.
- Running on a tree with no git produces zero history facts and says nothing about it, which is the
  precise failure mode `docs/kernel.md` warns about, a rule reporting zero being indistinguishable
  from a clean repository.

## Performance

flask `src/`, 24 files and 9,502 lines, best of three runs, wall clock.

| Tool | Time |
| --- | --- |
| Ruff, default rules | 8 ms |
| Ruff, `--select ALL` | 14 ms |
| jscpd | 66 ms |
| ty | 76 ms |
| vulture | 85 ms |
| Pyrefly | 130 ms |
| bandit | 253 ms |
| PMD CPD | 307 ms |
| **MCMR** | **827 ms** |
| pyright | 1,186 ms |
| Semgrep `p/python` | 1,449 ms |
| mypy | 1,638 ms |
| Pylint | 2,091 ms |
| refurb | 2,382 ms |
| CodeQL, database build plus analysis | 18,230 ms |

sqlalchemy `lib/`, 255 files and 247,908 lines.

| Tool | Time | Findings |
| --- | --- | --- |
| Ruff, default | 0.02 s | 175 |
| Ruff, `--select ALL` | 0.11 s | 58,077 |
| vulture | 1.59 s | |
| bandit | 5.16 s | |
| Semgrep `p/python` | 6.08 s | |
| refurb | 9.22 s | |
| **MCMR** | **14.04 s** | 13,189 failures, 13,121 findings |
| Pylint | 85.81 s | 19,288 |

MCMR sits between Semgrep and Pylint, which is a respectable place to be. What is not respectable is
where the time goes. The kernel self-reports 0.46 s of extraction on sqlalchemy `lib/`. The rules run
in 2.99 s. The remaining 7 s is transport.

| Phase, sqlalchemy `lib/` | Cost |
| --- | --- |
| JSON payload the kernel writes to the pipe | **287.0 MB** |
| subprocess spawn plus pipe | 2.85 s |
| decode the envelope | 1.70 s |
| validate 44,793 facts into Pydantic models | 2.44 s |
| kernel extraction itself | 0.46 s |

`SyntaxFact` alone is 122.7 MB of that payload for 13,435 declarations, `CallFact` is 42.4 MB,
`FunctionFact` is 33.8 MB. `docs/kernel.md` measured this on MCMR's own 357 files and found 139 ms of
transport for 5,336 facts, and concluded a PyO3 extension would save about 6 percent of a run. At
eight times the facts the transport is half the run, so that conclusion does not hold at scale. The
payload is the finding.

## Where MCMR should borrow next, ranked

`docs/backlog.md` ranks 26 items and every one of them is a new rule. That is the disagreement. With
70 of 214 deterministic rules already never firing on four real corpora, 37 percent of failures
printing a generic summary, and a flagship rule that reports 31 false positives where Ruff reports
zero, another rule raises the catalog count without raising what a user gets. The list below is what to
borrow, and none of it is in the backlog today.

**1. Fix the reference resolver, and exempt `__future__`.** Not a borrow so much as a debt. The
`elif` test, the `except` handler type, and the wildcard re-export are three false-positive classes in
the single most-used rule in the catalog, each with a repair attached. Ruff's binding model is
the reference implementation. Until this lands, `PY-IMPO0003` should stop claiming `Generalizes
Pylint W0611`, because a claim that fires 31 times where the oracle fires 0 is an overclaim.

**2. Give `ALL-ARCH0002` the graph that already exists.** `mcmr matrix` prints the cycle over the
same repository the rule says is acyclic. The module graph is built, the condensation is computed,
and the rule reads a different, per-file family that carries only external edges. This is one fact
family away and it closes MCMR's most visible parity claim against Pylint.

**3. Make every failure name a site and a specific thing.** Borrow the discipline rather than the
code. Ruff and Pylint have no concept of a diagnostic without a message about the code. 38 of 54
rules that fired on flask never state one. The `Finding` model already exists and the good rules
already use it, so this is a per-rule migration with a test that refuses a deterministic rule
without a finding, exactly as `tests/test_rule_findings.py` refuses one without a semantic case.

**4. A report of what did not fire.** Extend the honesty of `tests/test_fact_variation.py` from
fields to rules. `mcmr check` should be able to say how many rules were selected, how many received
evidence, and how many produced nothing, because today a rule that cannot fire and a clean repository
print the same thing, which is the exact failure mode the kernel document names as the worst shape a
rule can have.

**5. Suppression with justification.** Borrow `# noqa` and improve on it. MCMR already reads
suppression markers and already parses `reason=`, `since=`, and `expires=` off them for
`ALL-WAIV0001`. Honouring an `# mcmr: ALL-ENCA0001 reason=... expires=...` and then counting it as
debt would be strictly better than every suppression mechanism in this document, and it removes the
adoption blocker that a project cannot silence one rule.

**6. A project configuration file.** Borrow the shape from Ruff, not the philosophy. The rule is
the right override unit and deriving contracts is the right instinct. A project needs to name rules
it does not want, override one interval, and set per-path exceptions. `PY-DOCU0001` at 51 percent
of the output on a foreign repository is what the absence costs.

**7. Apply the fixes.** `docs/autofix.md` is a complete specification with nothing behind it. Borrow
Ruff's import editor and its safe-versus-unsafe split, both of which the document already names. 23
planned fixes and no `--fix` is the largest gap between what MCMR documents and what it does.

**8. Stream the payload per family, and stop sending trees nobody asked for.** 287 MB of JSON for 255
files is the scale problem. Emitting each family as separately addressable bytes is already named in
`docs/kernel.md` as the thing that unblocks handing Pydantic raw bytes, and it would let `SyntaxFact`
be paid for only by the rules that read it.

**9. SARIF output.** Every platform in the cross-language section speaks it, GitHub code scanning
consumes it, and `CheckReport` is already a structured model with one renderer. This is the cheapest
item on the list.

**10. Semgrep's pattern language for the house rules.** Backlog items 10 through 14 are pattern
matches and each currently costs a kernel change. A pattern rule that reads `SyntaxFact` and matches
against the neutral vocabulary would let a house rule be written without touching Rust, which is the
single biggest constraint on how fast the catalog can grow.

**11. Dataflow, eventually, and only where it pays.** 52 of the 73 Pylint messages MCMR records as
unavailable need an inferred type, and CodeQL's taint analysis is a whole judgment class MCMR cannot
enter. This is correctly last. Building inference to chase Pylint parity would mean rebuilding the
library Pylint already has, and the right answer stays delegation.

Where the existing backlog and this list agree, the existing ranking should stand. Items 4 through 9
of `docs/backlog.md`, large value passed by copy, wildcard imports, similar identifiers, undocumented
failure modes, and member ordering, are all reasonable rules. They should land after the nine items
above, not before.

## Known documentation and delivery gaps

- `docs/kernel.md` section K2g states "the ledger fell from 160 entries to 130". The ledger in
  `tests/test_fact_variation.py` today holds 92 invariant fields and 3 unfilled families.
- `docs/autofix.md` describes `--fix` applying safe plans and a backend that renders, verifies, and
  iterates. No `--fix` flag exists on any command and no renderer exists in the kernel.
- `SYSTEM.md` lists `cpp` among the rule scopes. The catalog has no `cpp`-scoped rule. Whether that
  is a gap or a naming artefact belongs to the C and C++ comparison rather than this one.

## Reproducing everything above

```bash
# MCMR's own inventory and accounts
chefe run coverage -- --tool pylint
chefe run coverage -- --tool ruff --state native
chefe run check -- /tmp/mcmr-cmp/flask/src --format concise --limit 2000
chefe run matrix -- /tmp/mcmr-cmp/flask/src

# the corpora
git clone --depth 200 https://github.com/pallets/flask.git       # 36e4a824
git clone --depth 200 https://github.com/encode/httpx.git
git clone --depth  50 https://github.com/sqlalchemy/sqlalchemy.git  # aa1a5575

# the upstream inventories
ruff rule --all --output-format json
python -c "from pylint.lint import PyLinter; from pylint.checkers import initialize; \
l=PyLinter(); initialize(l); print(len(list(l.msgs_store.messages)))"

# the tools, from a venv under /tmp so chefe.toml is untouched
uv venv /tmp/mcmr-cmp/.venv
uv pip install bandit vulture radon xenon pydocstyle darglint refurb perflint flake8 \
  flake8-bugbear flake8-comprehensions flake8-simplify flake8-bandit flake8-return \
  flake8-boolean-trap flake8-async flake8-todos flake8-print eradicate flake8-eradicate \
  flake8-annotations flake8-cognitive-complexity import-linter deptry pip-audit
uv venv /tmp/mcmr-cmp/.venv-wps && uv pip install wemake-python-styleguide
uv venv /tmp/mcmr-cmp/.venv-sem && uv pip install semgrep safety
npm install --prefix /tmp/mcmr-cmp/npm jscpd pyright

# CodeQL and PMD
curl -L -o codeql.tar.gz https://github.com/github/codeql-action/releases/download/codeql-bundle-v2.26.1/codeql-bundle-linux64.tar.gz
curl -L -o pmd.zip https://github.com/pmd/pmd/releases/download/pmd_releases%2F7.19.0/pmd-dist-7.19.0-bin.zip
```

The two defects reproduce from the minimal sources quoted in their own sections, written anywhere
outside this repository and run with `mcmr check --select unused_import` and
`mcmr check --select import_cycles`.
