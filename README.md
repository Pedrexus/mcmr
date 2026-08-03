# My Code, My Rules

MCMR is a fast code policy engine for whole repositories. A Rust kernel understands the source
tree once. Typed Python rules then query shared Polars tables and report precise findings. Rules
can also offer verified fixes.

MCMR currently reads Python, Rust, TypeScript, C, C++, and CUDA. Deterministic checks are local and
stateless. Contextual checks and network providers are explicit opt-ins.

## Try it

```sh
pip install mcmr
mcmr check .
```

Preview fixes without changing files.

```sh
mcmr check . --repair preview
```

Apply only fixes declared safe. MCMR reparses the result and reruns the originating rule before it
keeps an edit.

```sh
mcmr check . --repair apply
```

Enable contextual or network-backed rules only when the run needs them.

```sh
mcmr check . --contextual
mcmr check . --external
mcmr check . --contextual --external
```

Useful inspection commands include the following.

```sh
mcmr catalog
mcmr coverage
mcmr replacement
mcmr check . --format json
```

## Why it is different

- Every rule runs once over a typed table instead of once per object.
- The kernel extracts each selected fact family once.
- Rules own policy and repair intent while providers only retain evidence.
- A finding points to exact source and explains the measurement behind it.
- The default run creates no cache, history, or hidden evidence directory.
- Installed packages can add rules and external fact providers without editing MCMR.

## Plugins

A rule package publishes an `mcmr.rules` entry point. An external data integration publishes an
`mcmr.providers` entry point. Rules in that package request custom `Table[Fact]` types in the same
way built-in rules request source facts.

```toml
[project.entry-points."mcmr.rules"]
acme = "acme_mcmr.rules"

[project.entry-points."mcmr.providers"]
acme = "acme_mcmr.provider:AcmeProvider"
```

Provider settings stay in the checked repository configuration. Secrets stay in the provider's
chosen secret source.

```toml
[tool.mcmr.execution]
external = true

[tool.mcmr.providers.acme]
server = "http://localhost:8080"
```

## DataHub hackathon

MCMR began on July 23, 2026 and is being prepared for the
[Build with DataHub Agent Hackathon](https://datahub.devpost.com/). The planned showcase turns
DataHub schemas, lineage, ownership, and governance into typed facts. MCMR will use those facts to
review data code, repair proven problems, and write useful results back to the DataHub graph.

The target is one clear end-to-end workflow rather than a broad collection of shallow checks. See
[ROADMAP.md](ROADMAP.md) for the submission plan.

## Development

Chefe owns the environment and every task.

```sh
chefe install
chefe run lint
chefe run typecheck
chefe run test
chefe run core-lint
chefe run core-test
chefe run self-check
```

The package is Apache 2.0 licensed. [SYSTEM.md](SYSTEM.md) describes the contracts and
[docs/autofix.md](docs/autofix.md) explains repairs.
