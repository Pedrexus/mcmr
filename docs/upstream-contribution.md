# Upstream contribution draft

Ready to submit, not submitted. Nothing here has been opened against a DataHub repository. Review
the text, adjust anything that reads wrong, and post it yourself.

The contribution is one documentation page, because that is where the friction actually was. Every
GraphQL shape MCMR needed exists and works. Finding out which one to ask for, and in what nesting,
took longer than writing the code that consumed it.

## Where to open it

`datahub-project/datahub`, under `docs/api/graphql/`, as a new page titled **Reading a dataset for
an agent**. Open it as a pull request rather than an issue, since the whole value is the
copy-pasteable query.

## Issue text, if a discussion is wanted first

> **Title** GraphQL docs lack one complete dataset read for agent integrations
>
> Building a metadata-aware tool against DataHub Core, the first task is always the same. Read one
> dataset with its schema, ownership, domain, field-level tags and glossary terms, column-level
> lineage, and table-level lineage, then join that to something outside DataHub.
>
> Every piece of that is documented, and none of it is documented together. `searchAcrossEntities`
> is shown returning `urn` and little else. Field-level `globalTags` appear in the tags guide as a
> concept rather than as a selection under `schemaMetadata.fields`. `fineGrainedLineages` is
> described in the column-level lineage guide without a query that reads it back. `degree` on
> `searchAcrossLineage` is the field that separates a direct edge from a reachable node, and an
> integrator who misses it builds a lineage graph where everything is adjacent to everything.
>
> The result is that each new integration rediscovers the same five selections by trial against a
> live instance. A single page holding one worked read would remove that entirely.
>
> I would be glad to contribute the page. A draft is below.

## Page draft

````markdown
# Reading a dataset for an agent

An agent integrating with DataHub usually needs one thing before anything else: everything DataHub
knows about a dataset, in as few round trips as possible. This page is that read.

## The catalog page

One bounded search returns the governance an agent reasons over. `count` and `start` page it, and
`skipHighlighting` keeps the response small when the query is a wildcard.

```graphql
query DatasetPage($query: String!, $count: Int!, $start: Int!) {
  searchAcrossEntities(input: {
    query: $query
    count: $count
    start: $start
    types: [DATASET]
    searchFlags: { skipHighlighting: true }
  }) {
    total
    searchResults {
      entity {
        urn
        ... on Dataset {
          properties { description lastModified { time } }
          deprecation { deprecated }
          ownership {
            owners {
              owner {
                ... on CorpUser { urn username }
                ... on CorpGroup { urn name }
              }
            }
          }
          domain { domain { urn properties { name } } }
          schemaMetadata {
            fields {
              fieldPath
              type
              description
              globalTags { tags { tag { urn properties { name } } } }
              glossaryTerms { terms { term { urn properties { name } } } }
            }
          }
        }
      }
    }
  }
}
```

Three things are easy to miss here.

`ownership.owners[].owner` is a union, so a query that selects only `urn` silently loses the human
name a report wants to print. Spreading both `CorpUser` and `CorpGroup` is what gets you a usable
identity.

`globalTags` and `glossaryTerms` sit under each entry of `schemaMetadata.fields`, not on the
dataset. A tag applied through the UI may instead live under
`editableSchemaMetadata.editableSchemaFieldInfo`, so an integration that must see every label reads
both and merges them.

`properties.lastModified.time` is epoch milliseconds. Comparing it against a cutoff is how an agent
answers "which assets changed since my last run" without a second API.

## Column-level lineage

Column-level lineage is what proves a rename. When a column disappears from a schema and exactly
one surviving column derives from it, that is evidence rather than a guess, and it is the
difference between a tool that suggests a fix and a tool that can apply one.

```graphql
query FieldLineage($urn: String!) {
  dataset(urn: $urn) {
    urn
    fineGrainedLineages {
      upstreams { urn path }
      downstreams { urn path }
    }
  }
}
```

`path` is the field path, which is what joins back to `schemaMetadata.fields[].fieldPath`. The
`urn` on each side is a `schemaField` URN that embeds the dataset URN, so a consumer can tell an
intra-dataset rename from a cross-dataset derivation without a second lookup.

## Table-level lineage

`searchAcrossLineage` answers reachability, and `degree` is what turns it into a graph.

```graphql
query DatasetLineage($urn: String!, $count: Int!, $start: Int!) {
  searchAcrossLineage(input: {
    urn: $urn
    direction: DOWNSTREAM
    query: "*"
    count: $count
    start: $start
    searchFlags: { skipHighlighting: true }
  }) {
    total
    searchResults {
      degree
      entity { urn }
    }
  }
}
```

Keep `degree` equal to one when you are building edges. Every result is reachable from the URN you
asked about, so treating the whole response as adjacency produces a graph where the source appears
to feed the entire warehouse directly, and any impact measure computed over it is wrong in a way
that looks plausible.

## Writing a result back

An agent that concludes something should say so on the asset. Institutional memory is the right
place, because it is additive and editable.

```graphql
mutation AttachAnalysis($urn: String!, $url: String!, $label: String!) {
  addLink(input: { resourceUrn: $urn, linkUrl: $url, label: $label })
}
```

Prefer this over `updateDescription`. A description is usually a sentence a person wrote, and an
agent that overwrites it destroys the context the next reader needs. A link adds a claim beside the
existing ones and leaves the human record intact.
````

## What to say about the source

The page came out of building [MCMR](https://github.com/phvv-me/mcmr), a code policy engine that
joins DataHub context to source facts, for the Build with DataHub Agent Hackathon. Mentioning that
is honest and gives a reviewer somewhere to check the queries actually run. It is not a reason to
merge, so keep it to one line at the end of the pull request description.

## Before submitting

Every query on this page is the one MCMR sends, and each has been exercised against recorded
responses in this repository. **Run all four against a live DataHub Core instance first.** If a
selection is spelled differently on the running schema, fix it here before opening the pull request
rather than after. A documentation contribution whose examples do not execute is worse than none.
