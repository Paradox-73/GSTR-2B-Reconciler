# How we work

## Flow

1. Pick an issue from the board (or open one). Assign yourself so we don't both do it.
2. Branch off `main`: `feat/<issue-no>-short-name`, `fix/<issue-no>-short-name`, `infra/...`, `docs/...`
3. Commit in small steps. Message format: `type(scope): what changed`
   - types: `feat`, `fix`, `test`, `refactor`, `docs`, `ci`, `infra`, `chore`
   - e.g. `feat(matcher): normalise invoice numbers`
4. Open a PR, put `Closes #<issue-no>` in the description.
5. CI must be green (ruff + pytest). Squash merge. Delete the branch.

`main` is protected: no direct pushes, merge only through PRs.

## Rules we agreed on

- No secrets in git, ever. Not in `.env`, not in compose files, not in comments. They go in Vault (or a local untracked `.env` until Vault is up).
- No real client data in the repo. Use `datagen/`.
- Logs carry ids and counts only, never amounts or supplier names.
- If you change matching logic, the golden-set tests have to pass. If the expected output really should change, update `tests/golden/` in the same PR and say why.
- Questions and decisions go on the issue, not in DMs, so we have a record for the report.
