# Recorded DataHub example

One nightly rollup, one governed catalog, and no running service. Run it from the repository root.

```sh
mcmr demo
```

The command copies this directory into a fresh workspace, so nothing here is edited and the demo
runs the same way every time.

## The story

`pipeline.py` reads two assets the catalog governs.

- `ecommerce.analytics.orders` is owned and documented, but the query still names `legacy_total`.
  The catalog no longer declares that column, and its column-level lineage says `total` is the one
  column derived from it. `ALL-DATA0002` reports the exact line, and the proof licenses one safe
  rewrite that MCMR previews, applies, reparses, and reruns before keeping.
- `ecommerce.marts.invoices` has no owner and no description, so `ALL-DATA0013` reports the source
  line that depends on it. Nobody can review this change and nobody can say what the numbers mean.
- `customer_email` on `ecommerce.analytics.orders` is tagged `PII` with no glossary term, which
  `ALL-DATA0012` reports as a label nobody can act on.
- `ecommerce.raw.orders` has no owner at all and four assets sit downstream of it, which is
  what `ALL-DATA0011` reports. An unowned leaf costs one team an afternoon while an unowned root
  stops a reporting stack.
- `amount` is read through `CAST(amount AS STRING)` while the catalog declares it a number, which
  `ALL-DATA0003` reports after normalising both spellings through one engine-neutral parser.
- `since` marks the two assets DataHub modified this month as changed, so `ALL-DATA0007` judges
  the work in front of the reviewer rather than the whole catalog behind it.

## The recordings

`recordings/` holds one JSON file per GraphQL operation. Each file is a list of exchanges pairing
the request variables with the exact response envelope the server returned, so replay is a lookup
rather than a simulation.

```json
[{ "variables": { "urn": "..." }, "response": { "data": {}, "extensions": {} } }]
```

`pyproject.toml` selects them.

```toml
[tool.mcmr.providers.datahub]
recorded = "recordings"
```

**These recordings are authored rather than captured.** They follow the response shapes
`mcmr_datahub/provider.py` already parses and the DataHub GraphQL schema documents, built around
the showcase ecommerce datapack. Re-capturing them against a running GMS is a file swap, because
the stored `response` is the envelope verbatim. Until that happens the exact spelling of
`Dataset.fineGrainedLineages` and of the field-level `globalTags` and `glossaryTerms` selections is
the one claim here that a live endpoint has not yet confirmed.

`MCMRWriteback.json` records the mutation `mcmr writeback` posts. Writeback is never part of a
check, so only that command reaches it.

`ALL-DATA0008` stays skipped. It measures the share of a breaking change's blast radius that no
test evidence covers, and neither the breaking judgment nor the test evidence has an honest source
here. A working-tree diff says a file moved, not that a schema broke, and nothing in this
repository maps a test to the asset it exercises. Reporting a fabricated hundred percent gap would
be worse than reporting nothing, so the rule stays visible as skipped.

`ALL-DATA0006` stays quiet for the same reason. Upstream health needs DataHub assertion results,
which DataHub Core rarely populates, so authoring a recording that claims them would describe a
service the judge cannot reproduce.
