# Table rule execution

MCMR executes its complete 279-rule catalog over typed Polars tables built by the Rust kernel.
Tables are the production boundary and the rule authoring surface. A check does not reconstruct
Pydantic facts, dispatch one Python call per fact, or keep an alternate row executor.

## Invariants

The completed engine keeps these properties.

- All 279 rules accept one or more typed `Table[Fact]` dependencies.
- Each of the 216 deterministic rules is invoked once and returns one lazy Polars query.
- Each of the 65 contextual rules is invoked once and returns one lazy candidate query.
- Each contextual rule makes one batched backend call after its candidate query is collected.
- Python receives aggregate rule rows and only the bounded failures needed for reporting.
- Successful observations never materialize their source evidence as Python objects.
- Retained evidence is normalized directly from native relations.
- The native session emits table markers only. It has no JSON fact stream or temporary spool.
- There is no execution setting that selects a row or table implementation.

These are architectural constraints rather than optional optimizations. A new rule that requires
per-fact invocation or a provider that sends nested fact objects across the native boundary would
reintroduce the overhead this design removes.

## Rule contract

Any required parameter may name a typed family table. The first table supplies the stable output
identity, while every further table supplies relations the rule may join or aggregate. A
deterministic rule states one relational plan and returns a `RuleQuery`. Findings remain lazy
relations linked by stable fact identity.

```python
@rule("PY-IMPO0003")
def unused_import(subject: Table[ImportBindingFact]) -> OccurrenceQuery:
    frame = subject.lazy(ImportBindingRelation.FACTS)
    value = (
        (pl.col("reference_count") == 0)
        & ~pl.col("is_reexported")
        & ~pl.col("is_type_only")
    )
    return RuleQuery.boolean(
        frame,
        value,
        findings=FindingQuery.precise_boolean(frame, value, "unused import"),
    )
```

`Table[Fact]` is dependency injection. The fact type selects the native schema and the relation
enum selects the exact data the query needs. A rule may request `Table[CallFact]` and
`Table[FunctionFact]` together, then join those lazy relations in the same plan. Settings remain
keyword-only literals compiled into the query. Services remain required typed parameters. The
catalog validates the whole signature once before execution.

The planner partitions selected rules into connected dependency graphs. A rule requesting two
families connects those families, so the native session materializes both before planning that
rule. Independent components still execute and release their tables separately, which preserves
bounded peak memory without restricting joins.

## Typed relations

The table grain follows the entity a rule filters, counts, joins, or reports. A module-sized fact
that contains repeated records becomes a parent relation and child relations rather than one cell
holding a Python list.

Every reportable row carries stable fact identity, source path, language, ordering, and source span.
Child rows also carry their parent identity and ordinal. Graph families use node and edge relations.
Expression families use flat parent, child, and root identities. Bounded syntax walks stay in Rust
when moving a tree into columns would only recreate traversal in Python.

Common shapes include the following.

| Evidence | Normalized form |
| --- | --- |
| Functions and classes | Declaration rows with keyed parameter, member, control, and decorator rows |
| Calls and expressions | Call, argument, keyword, expression, mapping, binding, and evidence rows |
| Imports and references | Binding, use, source node, and retained evidence rows |
| Pydantic models | Separate model and field rows |
| Repository graphs | Node and edge rows with stable repository identities |
| Contextual inputs | Generic fact, record, value, and evidence rows |

Specialized relations preserve efficient deterministic queries. The native session can also expose
generic mirrors for families used by contextual rules. Those mirrors have the same stable fact
identity, which lets one contextual query package fields, repeated records, values, and evidence
without reconstructing the original fact model.

## Deterministic execution

Each deterministic declaration contributes one `RuleQuery`. The query carries a lazy value
relation and an optional lazy finding relation. Value rows use one normalized schema with rule
identity, fact identity, answer kind, and scalar answer. Finding rows carry only message data,
measurements, exact source span, repair identity, and retained evidence references.

The runner invokes each selected rule once. Polars performs row filtering, aggregation, joins,
sorting, and expression simplification. Every table relation exposes one shared `LazyFrame` root.
That root is a reusable query plan rather than a cached result, so the collector gives related
branches to `pl.collect_all` in one execution unit. Polars can then recognize common subplans and
insert cache nodes instead of evaluating each branch independently.

Collection has two phases. The first multiplexes compact summaries and bounded failure identities.
The second runs only when failures exist and multiplexes findings, rewrites, nodes, and imports for
the retained identities. A zero-finding scan therefore never evaluates detailed evidence plans.
Policy judges the compact results without revisiting source rows.

Only failures inside the configured report limit materialize detailed findings. Counts remain exact
past that limit, so bounded reporting never changes a verdict. Retained source, nodes, references,
and repair inputs come directly from normalized relations and are reconstructed only for those
bounded failures.

Production statistics report table queries and observations. There is no row-call counter because
there is no row execution path to count.

## Contextual execution

Contextual rules use the same typed table injection and one-call contract. Their return value is a
`ModelQuery` rather than a `RuleQuery`.

```python
@rule("ALL-COMM1001")
def comment_intent(
    subject: Table[CommentFact],
    backend: ClassificationBackend,
) -> ModelQuery[CommentIntent]:
    return backend.classification(
        subject,
        category=CommentIntent,
        instructions=comment_intent.instructions,
    )
```

One lazy candidate query applies path and language selection, orders candidates, groups repeated
records, and encodes only the normalized subject fields and evidence the model contract needs. The
backend receives that candidate frame through one batched call for the rule. It may process the
batch concurrently behind its interface, but the rule and runner still observe one request.

Classification answers become category rows. Assessment answers become typed criterion rows and a
deterministic Polars decision table reduces them to the final category. Confidence, citations,
token use, model identity, and reasoning effort stay attached as finding provenance. The resolved
result is an ordinary `RuleQuery`, so policy and reporting do not need a second model executor.

## Native boundary

The mixed Maturin project exposes `mcmr.kernel_tables` through PyO3 and `pyo3-polars`. One
`AnalysisSession` performs discovery, parsing, extraction, and graph enrichment, then retains only
the selected typed records. It constructs a family's eager `PyDataFrame` relations when the
coordinator consumes that family's marker, and Python makes those frames lazy for planning. Generic
schemas are likewise compiled only when their family is consumed.

The native session emits a marker for each available typed family. A marker tells the Python
coordinator which registered table to retain and execute. It does not name a JSON payload, spool
file, or compatibility representation. A selected family is normalized once and released after its
queries and bounded evidence collection finish. Families later in the marker stream do not hold
normalized Polars frames while an earlier family runs.

Direct `PyDataFrame` transfer keeps Rust and Python on the same Polars buffer boundary. Internal
Rust records never become Python dictionaries. MCMR states `gil_used = false`, detaches discovery
and table construction from Python, lets Rayon own native parallel work, and lets Polars own query
parallelism.

The standalone kernel binary remains useful for native development and provider inspection. It is
not an alternate production rule engine and does not define a parity fallback.

## Engine study

Polars currently offers in-memory, streaming, and GPU execution for lazy plans. MCMR keeps the
ordinary in-memory engine after measuring the alternatives rather than assuming that a newer
engine fits this workload.

The current repository self-scan measured the same 177 queries and 213,582 observations under both
CPU engines. In-memory execution took 801 ms for rules and reached 1,306,936 KiB peak RSS. Streaming
execution took 4,429 ms for rules and reached 2,524,280 KiB peak RSS. Streaming was 5.53 times
slower for the rule stage and used 1.93 times the peak memory. MCMR starts from in-memory native
frames and runs many compact joins and grouped queries, so batching did not produce the source
pushdown or memory benefit it can provide for file scans.

GPU execution remains an explicit experiment rather than a default. Polars GPU support is an open
beta backed by `cudf-polars`. It supports joins, filters, strings, and grouped aggregations, which
match much of MCMR. It does not support several data types and operations MCMR also uses, including
some list operations, arrays, binary data, folds, and user-defined functions. One unsupported
operation makes an ordinary GPU request run the complete query on CPU. Any MCMR benchmark must use
`pl.GPUEngine(raise_on_fail=True)` so it cannot mistake fallback for GPU execution.

The local RTX 4090 satisfies the hardware requirement, though `cudf-polars` is not part of the
development environment. Installing a large GPU runtime is not justified until representative
plans pass strict GPU validation and their data volume can amortize CPU to GPU transfer and
startup. Final Polars results return to CPU memory either way.

## Current measurement

The 2026-07-30 uncached self-check exercised the completed deterministic engine over 593 files and
28,509 facts. The run planned 177 queries for the families present in that repository and produced
213,773 observations. Native work took 1,679 ms and rule work took 575 ms.
The observation count includes successful rows while Python retained only aggregate results.

An independent Mainboard run measured 2,934 ms for the whole command, which is 202 files per
second. Native extraction owns about three fifths of that wall time. The complete relational rule
stage owns about one fifth and processes roughly 1,063 repository files per second. Python 3.14
cannot expose Tachyon samples, so this measurement records the native spans and the built-in stage
timings. Function-level Python sampling remains a Python 3.15 follow-up.

The count of planned queries varies with selected rules, available languages, provider output, and
model configuration. The invariant is one invocation per runnable declaration, never one invocation
per fact.

## Historical migration measurements

The following measurements compare transitional implementations. They remain useful evidence for
why the final boundary is relational, but they do not describe a path that still exists.

The first FunctionFact pilot analyzed 533 files and 2,969 function rows.

| Historical stage | Time |
| --- | ---: |
| Rust kernel | 106 ms |
| JSON parse and normalization | 26 ms |
| Python dictionaries into Polars | 67 ms |
| Pydantic validation | 76 ms |
| Five fused Polars rules | 0.99 ms |
| Five row-dispatched rules | 67.1 ms |

The complete FunctionFact comparison covered 547 files, 3,187 callable rows, 21 deterministic
rules, and 58,887 evaluations.

| Historical slice | Row prototype | Table prototype | Improvement |
| --- | ---: | ---: | ---: |
| Scalar rule engine median | 551 ms | 35.7 ms | 15.5 times |
| Repeated complete judgment median | 548 ms | 340 ms | 1.61 times |
| Complete judgment files per second | 998 | 1,610 | 1.61 times |

The complete CallFact comparison covered 555 files, 25,983 normalized calls, 18 deterministic
rules, and 8,438 evaluations.

| Historical slice | Row prototype | Table prototype | Improvement |
| --- | ---: | ---: | ---: |
| Scalar rule engine median | 104.4 ms | 32.1 ms | 3.26 times |
| Complete judgment median | 1,211 ms | 663 ms | 1.83 times |
| Complete judgment files per second | 458 | 837 | 1.83 times |
| Kernel and transfer time | 1,142 ms | 526 ms | 2.17 times |

Those pilots also showed why nested Arrow rows were not enough. Flat CallFact relations retained
about 27 MiB where equivalent Pydantic construction retained about 243 MiB. Flattening structure
and eliminating duplicate representations mattered more than wrapping existing objects in a
DataFrame.

## Extending the engine

A new fact family needs native normalized relations, stable identities, a relation enum, and a
registered `Table[Fact]` constructor. A new deterministic rule requests every table it needs and
adds one lazy `RuleQuery`. A new contextual rule adds one lazy `ModelQuery` and a closed category or
decision table. Neither change adds coordinator branches, row adapters, or transport formats.

MCMR deliberately keeps no run history or cross-run database. Polars expression plugins remain
available when a stable operation cannot be stated clearly with ordinary expressions.

## Primary references

- [Polars query optimizations](https://docs.pola.rs/user-guide/lazy/optimizations/)
- [Polars multiplexing queries](https://docs.pola.rs/user-guide/lazy/multiplexing/)
- [Polars streaming](https://docs.pola.rs/user-guide/concepts/streaming/)
- [Polars GPU support](https://docs.pola.rs/user-guide/gpu-support/)
- [Polars Arrow producer and consumer guidance](https://docs.pola.rs/user-guide/misc/arrow/)
- [Polars expression plugins](https://docs.pola.rs/user-guide/plugins/expr_plugins/)
- [`pyo3-polars` `PyDataFrame`](https://docs.rs/pyo3-polars/latest/pyo3_polars/types/struct.PyDataFrame.html)
- [PyO3 free-threaded Python guidance](https://pyo3.rs/v0.29.0/free-threading.html)
- [Maturin mixed Rust and Python layout](https://www.maturin.rs/project_layout.html)
