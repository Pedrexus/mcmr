# My Code, My Rules

MCMR defines engineering policy as 277 typed Python rules over Python, Rust, TypeScript, C, C++,
and CUDA. A Rust kernel extracts shared facts, builds the repository graph, and feeds only the
evidence each rule declares.

Its reference table accounts for the frozen Pylint, Ruff, Clippy, ESLint, typescript-eslint,
clang-tidy, and cppcheck inventories. Coverage claims are checked against each tool's language
boundary and executable oracle comparisons hold overlapping rules to the upstream result.

```sh
pip install mcmr
mcmr check src
mcmr snapshot .
mcmr diff .
mcmr trend .
mcmr floor
```

Development uses Chefe.

```sh
chefe install
chefe run lint
chefe run typecheck
chefe run test
chefe run floor
chefe run build
```

See [SYSTEM.md](SYSTEM.md) for the current contract and phase boundary,
[docs/autofix.md](docs/autofix.md) for how fixes are written and applied, and
[docs/generalization.md](docs/generalization.md) for how rules reach beyond one language, and
[docs/backlog.md](docs/backlog.md) for what comes next.
