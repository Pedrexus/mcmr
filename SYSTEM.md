# MCMR system

MCMR turns repository policy into typed queries. It separates source understanding, rule logic,
judgment, repair, and presentation so each boundary can be tested independently.

## Nonnegotiable properties

- One repository walk supplies one request.
- One selected fact family is extracted once.
- One rule is invoked once.
- A rule receives only the tables and services named by its signature.
- Providers retain primitive evidence and never decide a rule's verdict.
- Rules never clamp illegal provider values.
- A normal run is stateless and writes nothing unless the user requests a report or repair.
- Contextual and network work stays disabled unless explicitly enabled.
- A fix is kept only after syntax validation and a fresh rule check.

## Execution flow

```text
configuration
    |
catalog and plugin discovery
    |
selected rule signatures
    |
fact family dependency graph
    |
Rust source kernel plus enabled external providers
    |
typed repository tables
    |
one lazy query per rule
    |
policy judgment and bounded evidence
    |
Rich, plain, or JSON report
    |
optional preview or verified application
```

The planner groups rules whose table dependencies connect. Each group receives shared tables and
releases them after its queries finish. Polars collects summaries first. Detailed findings and
repair rows are collected only for retained failures.

## Source layout

`src/core` is the Rust kernel and PyO3 extension. It owns discovery, parsing, repository graphs,
primitive evidence, and direct Polars frames.

`src/api` is the Python API and CLI. It owns contracts, configuration, dependency injection,
query planning, judgment, rendering, and plugin discovery.

`src/rules` is the built-in rule distribution. It depends on the API just like a third-party rule
package does.

This split keeps the public extension surface in Python while measured source work remains in
Rust.

## Facts and tables

A `Fact` is one independently identifiable unit of evidence. Fact models define the provider
schema and legal value domain. Constrained types make impossible counts, percentages, paths, and
identities fail at the provider boundary.

Production queries do not loop over Pydantic objects. The kernel normalizes facts into typed Polars
relations. `Table[FunctionFact]`, `Table[CallFact]`, and other table types expose those relations
without hiding collection or joins.

Rules derive conclusions from primitive columns. A provider may retain a call target, a source
span, a reference count, or a graph edge. It may not retain a field such as `should_move` that
already answers the rule.

The first table in a rule signature supplies output identities. Additional tables provide joinable
evidence. Language annotations can narrow any table before the rule runs.

## Rule declaration

Every built-in rule lives below a path shaped like the following.

```text
mcmr.rules.<scope>.<lane>.<family>.<optional groups>.rNNNN
```

The explicit identifier remains searchable. The path independently validates its scope, lane,
family, and continuous number. Duplicate identifiers and numbering gaps fail catalog construction.

```python
@rule("PY-IMPO0003", fix_safety=FixSafety.REVIEW)
def unused_import(subject: Table[ImportBindingFact]) -> OccurrenceQuery:
    frame = subject.facts()
    value = (pl.col("reference_count") == 0) & ~pl.col("is_reexported")
    return RuleQuery.boolean(
        frame,
        value,
        findings=FindingQuery.precise_boolean(frame, value, "unused import"),
    )
```

Required parameters are injected tables or explicit services. Keyword-only parameters with
defaults are user settings. A rule returns one Boolean, count, percentage, category, or contextual
query. Policy belongs to the decorator and can be overridden by project configuration.

Rule documentation is part of the contract. It states a summary, definition, evidence,
exceptions, examples, and references. Catalog tests validate the format and upstream references.

The complete rule docstring follows this page order.

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

Every reference line is held to the parser's own grammar.

```
(?P<url>https?://\S+)
|(?P<relation>Generalizes|Adapts|Cites) (?:"(?P<work>[^"]+)"(?:, (?P<locator>.+))?
|(?P<tool>[A-Za-z][A-Za-z0-9-]*)(?P<identity>(?: [A-Za-z0-9][\w.-]*){1,2}))
```

## Rule plugins

An installed package exposes a module or package through the `mcmr.rules` entry point group.

```toml
[project.entry-points."mcmr.rules"]
datahub = "mcmr_datahub.rules"
```

Discovery imports leaf modules in stable order. Plugin rules use the same identifiers,
documentation, typing, numbering, policy, and query validation as built-ins. IDs are globally
unique.

A rule-only package depends on `mcmr-api`. It does not need the built-in rule distribution.

## External fact providers

An external provider owns one or more custom fact families and exposes a callable factory through
the `mcmr.providers` entry point group.

```toml
[project.entry-points."mcmr.providers"]
datahub = "mcmr_datahub.provider:DataHubProvider"
```

The entry point loads a zero-argument factory. Its instance implements the structural
`FactProvider` protocol. MCMR gives each invocation a `ProviderContext` with the repository, named
settings, requested families, and only the typed tables declared by each output family.

```python
from mcmr.facts import DataAssetFact, Fact
from mcmr.plugins import ProviderContext, RepositoryTables, provider


@provider
class DataHubProvider:
    families = {DataAssetFact: set()}

    async def tables(self, context: ProviderContext) -> RepositoryTables:
        ...
```

Provider ownership is exact. Two providers cannot claim the same requested family. The `families`
mapping states each output family and only the typed inputs needed to build that output. A provider
must return every requested family it owns and no others. These dependencies form one validated
acyclic graph. Native dependencies are materialized once and reused if a rule also reads them. The
engine skips rules whose families are not available.

Provider settings live under `tool.mcmr.providers.<entry point name>`. The core treats values as
validated JSON and does not interpret vendor options. A provider chooses how to obtain secrets.

External fact classes set `external_evidence` to true. This keeps their rules out of ordinary
offline runs. The command must enable `--external` or the equivalent configuration before any
provider loads or performs network work.

The bundled DataHub plugin calls `${DATAHUB_GMS_URL}/api/graphql` directly with HTTPX. It reads an
optional bearer token from `DATAHUB_GMS_TOKEN` and retains no response cache. Its SQLGlot resolver
joins literal SQL table and field references to exact catalog identities. Ambiguous names remain
unresolved instead of becoming guesses. It also retains the exact string literal that named each
field, which is the anchor a verified repair edits, and the column the asset's own fine-grained
lineage proves replaced a retired one.

A `recorded` setting names a directory of captured exchanges instead of a live server. One JSON
file per operation holds request variables beside the exact response envelope, so replay is a
lookup rather than a simulation and a live capture is a drop-in replacement. `mcmr demo` runs the
complete workflow over one such recording with no service, no network, and no edit to the example.

## Result publication

A provider that can write a completed run back to its own system implements `ResultPublisher`
beside `FactProvider`. Publication is not part of reading evidence, so no analysis path reaches it
and no configuration turns it on. Only `mcmr writeback` calls it, and it passes the governed assets
the run actually named rather than the whole catalog.

The bundled DataHub publisher attaches one institutional memory link to each of those assets
through `addLink`. That aspect is additive and editable, so a tool states what it found without
overwriting a sentence a person wrote. `updateDescription` would do the opposite, which is why an
agent must not reach for it.

The official `datahub` CLI remains useful for setup and diagnostics. DataHub MCP is a separate
agent surface for targeted lineage exploration and verified writeback. It does not become the
product transport or a hidden MCMR dependency.

## Contextual rules

Contextual rules build typed candidates from local tables. The engine batches candidates and calls
one explicitly configured classification backend. A backend returns closed categories with
provenance rather than free-form findings.

A category name states what the model observed and never what the engine will do with it, so the
prompt carries the project's own outcome map beside the rule instructions. Each category is named
with what selecting it reports, drawn from the resolved policy through `Policy.reported`, and the
model is told to answer what the evidence states rather than what it would prefer to report.

Contextual execution is separate from external evidence. A local model rule needs `--contextual`.
A DataHub-backed deterministic rule needs `--external`. A DataHub-backed contextual rule needs
both.

Four backends answer that contract. `gliner2` runs local weights, `codex` and `claude` each run one
isolated schema-constrained process per bounded batch, and `openrouter` posts the same closed schema
to an OpenAI-compatible server and reads its key from `OPENROUTER_API_KEY`. Every process and HTTP
backend shares one prompt, schema, and citation protocol, so a batch reaching a new provider changes
transport alone. `mcmr model-sweep . --backend <name> --model <model>` exercises every contextual
rule through one of them without editing the project.

## Repairs

A rule declares repair safety once on `@rule`. `FixQuery` does not repeat it. Compilation rejects a
rule that declares safety without returning a fix or returns a fix without declaring safety.

`FixQuery` carries a summary and three normalized relations.

- Rewrites state typed operations such as remove, replace, move, unwrap, rename, and inline.
- Nodes retain exact source anchors used by those operations.
- Imports state bindings the rendered replacement needs.

Nodes and imports default to typed empty relations. A simple path deletion therefore supplies only
its rewrite relation.

The query selects the same `fact_id` values that produced the finding. It does not call the
provider again. The collector materializes only failed repair rows and converts them to immutable
rewrite models.

The Python renderer validates retained source and UTF-8 byte spans. It manages runtime,
`TYPE_CHECKING`, and relative imports. Cross-file moves must name an existing destination and exact
anchors. The renderer rejects stale source, overlapping edits, incomplete references, unsupported
language operations, and syntax failures.

Safe application is transactional. MCMR writes one candidate atomically, reparses it, reruns the
originating rule, and keeps it only when the precise finding declines. Review repairs are preview
only.

Directory relocation remains intentionally stricter than a source move. A safe pathway collapse
must merge package initializers, prove collision freedom, rewrite every import and module identity,
and validate both Python and Rust module semantics. A file move without those proofs is not an
autofix.

## Configuration and state

MCMR reads configuration from `pyproject.toml`.

```toml
[tool.mcmr.execution]
deterministic = true
contextual = false
external = false

[tool.mcmr.contextual]
backend = "codex"
model = "gpt-5.6-terra"
reasoning_effort = "medium"
```

The default check constructs all requested tables in memory. It creates no `.mcmr` directory,
cache, historical report store, or evidence database. An explicitly named report is ordinary user
output rather than hidden state.

## Verification

The validation stack has distinct responsibilities.

- Rust unit tests hold parser, graph, and provider semantics.
- Focused rule tests state positive cases and documented exceptions.
- Property tests sweep complete model domains and reject impossible outputs.
- Variation ledgers fail in both directions when provider fields become constant or start varying.
- Catalog tests validate identity, numbering, documentation, policy, dependencies, and repairs.
- Oracle tests compare overlapping behavior with upstream tools.
- Coverage gates require complete statement and branch coverage.
- The self-scan runs MCMR over its own source tree.

Test volume is also analyzed as repository structure rather than accepted as a proxy for quality.
The kernel records each collected test's literal-neutral body, assertion shapes, fixture closure,
direct production calls, and transitive production reach. Rules use those relations to find exact
duplicate intent, repeated whole-graph reach, low-diversity production hotspots, broad literal
families that should become Hypothesis properties, and module-generated parametrizations that can
silently multiply collection. Findings remain review signals because static reach cannot prove that
runtime behavior, marks, or domain meaning are redundant.

The main contribution gate is the following.

```sh
chefe run contribute
```
