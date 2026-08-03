# My Code, My Rules

Define and enforce the engineering rules that make your code yours.

## Working Rules

- Keep the public surface small and documented.
- Prefer one boring command per task such as install, lint, typecheck, test, build, and publish.
- Update `README.md`, `SYSTEM.md`, and `CHANGELOG.md` when behavior changes.
- Do not add stack details to the README unless users need them to install or run the project.
- Do not commit, tag, publish, or push unless explicitly asked.

## Commands

The development environment and tasks are owned by `chefe.toml`.

- Install with `chefe install`
- Lint with `chefe run lint`
- Typecheck with `chefe run typecheck`
- Test with `chefe run test`
- Measure the mock floor with `chefe run floor`
- Build the core crate with `chefe run core-build`, test it with `chefe run core-test`, and lint it
  with `chefe run core-lint`
- Analyze a repository with `chefe run check <path>`
- Build with `chefe run build`
