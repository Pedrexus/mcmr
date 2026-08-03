# Roadmap

MCMR is targeting version 0.0.1 and the
[Build with DataHub Agent Hackathon](https://datahub.devpost.com/). The submission deadline is
August 10, 2026 at 5 PM EDT, which is August 11 at 6 AM JST. The internal feature freeze is August
9 at noon JST so the last day belongs to the demo and submission.

MCMR began on July 23, 2026, inside the allowed July 6 through August 10 development period. The
submission should state that date plainly.

## Product position

The submission is a metadata-aware code guardian.

MCMR reads source structure and DataHub context together. It finds a risky data-code change,
explains the affected assets and owners, repairs what it can prove, reruns the policy, and writes a
useful result back to DataHub for the next person or agent.

The primary category is Agents That Do Real Work. Metadata-Aware Code Generation and Development
is a strong secondary fit because verified fixes produce mergeable code artifacts.

The winning demo is one complete workflow. It is not a catalog of unrelated lint rules and it is
not another chat interface over metadata.

## Foundation already complete

- [x] Rust discovery, parsing, graph, and typed Polars boundary
- [x] One invocation and one lazy query per rule
- [x] Deterministic, contextual, and external execution lanes
- [x] Stateless in-memory execution
- [x] Exact findings with Rich, plain, and JSON output
- [x] Typed rewrite algebra with preview and verified safe application
- [x] Installed rule packages through `mcmr.rules`
- [x] Installed external fact providers through `mcmr.providers`
- [x] Named provider configuration under `tool.mcmr.providers`
- [x] Python, Rust, TypeScript, C, C++, and CUDA frontends
- [x] Upstream inventories, reference accounting, and executable oracle comparisons
- [x] GE4M replacement ledger
- [x] Full lint, typing, Rust, test, and coverage gates before the current work

## Hackathon critical path

### August 3 and 4

- [ ] Add a small `mcmr-datahub` package in this repository
- [ ] Use the DataHub MCP Server or Agent Context Kit as the required integration
- [ ] Keep DataHub credentials outside checked configuration
- [ ] Define typed facts for assets, fields, lineage, ownership, governance, and writeback results
- [ ] Load only the fact families selected rules request
- [ ] Use the showcase ecommerce datapack for the reproducible demo
- [ ] Record any DataHub SDK or documentation friction for the feedback prize

### August 5 and 6

- [ ] Implement a schema compatibility rule tied to exact source references
- [ ] Implement an unowned high-impact asset rule using downstream lineage
- [ ] Implement a sensitive-field governance rule using tags and glossary context
- [ ] Implement a changed pipeline without matching DataHub documentation or ownership rule
- [ ] Give each rule one positive case, one exception, and one end-to-end fixture
- [ ] Add one conservative repair that a judge can preview and apply live
- [ ] Write the verified result back to DataHub as durable context

Four deep rules are enough. More rules only help when they strengthen the same story.

### August 7

- [ ] Build one command that starts or connects to the sample DataHub environment
- [ ] Build one command that runs the complete MCMR demonstration
- [ ] Include the broken input, findings, patch, clean rerun, and DataHub writeback in `examples`
- [ ] Ensure the workflow works from a clean checkout with no private service
- [ ] Measure cold and warm time and keep the live portion comfortably below one minute

### August 8

- [ ] Make one meaningful upstream DataHub contribution
- [ ] Prefer a reusable DataHub Skill, connector improvement, SDK fix, or documentation repair found
  while building the integration
- [ ] Open the contribution early enough that judges can inspect it even if review is unfinished
- [ ] Complete the actionable feedback submission

### August 9

- [ ] Freeze features at noon JST
- [ ] Run all MCMR and DataHub integration gates from a clean checkout
- [ ] Run the demo three times without manual recovery
- [ ] Capture screenshots and sample JSON output
- [ ] Write the Devpost description in plain English
- [ ] Record a video no longer than two minutes and forty seconds
- [ ] Show the product working in the first twenty seconds

### August 10

- [ ] Publish the repository under Apache 2.0
- [ ] Make the license visible in the GitHub repository summary
- [ ] Provide exact setup and test commands
- [ ] Provide a free working demo or test path through the judging period
- [ ] Upload the public video and verify it in a signed-out browser
- [ ] Submit early and recheck every link

## Judging plan

The official criteria are equally weighted. Each needs visible evidence.

### Use of DataHub

Read schemas, lineage, ownership, and governance through an approved DataHub agent integration.
Join that context with exact source facts. Write the verified outcome back to the graph. A provider
that only copies metadata into a lint message is too shallow.

### Technical execution

Keep the workflow deterministic where facts suffice. Use contextual judgment only for a genuinely
semantic decision. Show typed provider boundaries, precise locations, one safe repair, a clean
rerun, and complete tests.

### Originality

Position MCMR as the bridge between code policy and the live organizational context graph. DataHub
understands data assets while MCMR understands the repository that creates and consumes them. The
joined graph can answer questions neither system answers alone.

### Real-world usefulness

Use a failure that data platform teams recognize. A renamed or sensitive field reaches a pipeline
change and several downstream assets while ownership is incomplete. The output must tell the
developer what changed, who is affected, and what can safely happen next.

### Submission quality

Keep the README short. Keep setup to one path. Commit sample outputs so judges can understand the
result without running DataHub. The video should follow one story from broken change to durable
resolution.

### Open-source bonus

Contribute one artifact upstream. A small accepted fix or useful Skill is stronger than a large
unreviewed proposal.

## Three-minute demo storyboard

1. Show one pull request with a realistic data pipeline defect.
2. Run MCMR and show exact source evidence plus DataHub lineage and ownership.
3. Preview and apply one proven repair.
4. Rerun MCMR and show the finding closed.
5. Open DataHub and show the result written back for the next agent.
6. End with the one-command setup, tests, and upstream contribution.

## Version 0.0.1 completion

- [ ] Self-scan has no unexplained failures and fewer than one hundred total issues
- [ ] Every selected deterministic rule runs or states an exact provider gap
- [ ] Contextual rules have a reviewed quality sample and explicit cost report
- [ ] `MODU003` previews only cohesive moves into existing sibling modules
- [ ] Repair safety is declared once and optional repair relations default cleanly
- [ ] The new suppression rule has a stable preview and semantic cases
- [ ] README, system contract, roadmap, changelog, and autofix documentation agree
- [ ] `chefe run contribute` passes
- [ ] Package builds from a clean checkout
- [ ] The DataHub demo passes from a clean checkout

## Deferred until after submission

- Typed package relocation for directory pathway collapse
- Incremental source caching
- GPU execution for Polars
- A web dashboard
- Broad marketplace discovery
- Additional contextual models
- More language frontends

Directory pathway collapse is deferred because moving files without merging initializers and
rewriting every module reference can create a new error while closing the directory finding. It
becomes an autofix only after one typed relocation transaction proves the entire change.
