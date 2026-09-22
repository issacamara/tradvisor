# Tradvisor V1 agent instructions

- Work against the `V1` integration branch and the published [Gate 2 baseline](https://github.com/issacamara/tradvisor/issues/1) and [tracking epic](https://github.com/issacamara/tradvisor/issues/2). Read the whole assigned issue and its linked baseline comments before changing code.
- Keep Swing, Long-Term Growth/dividend research, and manual recommendation-linked paper trading equal in V1. Real portfolio tracking, automated broker trades, Dividend/Balanced composite scoring, and additional indicator families are outside V1.
- Preserve existing ingestion and development resources. Do not copy production state, data, users, or secrets. Do not run cloud plans, applies, migrations, paid queries, seeding, or schedule activation without the separate approval specified in the architecture.
- The public GitHub issues contain sanitized contracts. Private infrastructure evidence stays local and must not be copied into commits, PRs, comments, logs, or agent output.
- One implementation ticket per agent. Confirm hard dependencies by merged PR or equivalent artifact on `V1`, not by issue closure alone. Respect conflict exclusions and file reservations in the epic.
- Work in an isolated branch/worktree from current `V1`; leave unrelated working-tree changes untouched. Use `feature/<issue-number>-<slug>` and one PR per ticket with `Closes #<issue-number>`.
- Run applicable local checks and wait for current-head CI. Require independent review of the current head before merging. Stop for a major product, financial, security, architecture, cost, or infrastructure decision; send the owner evidence, options, and a recommendation.
- Agent role instructions live in `.codex/agents/`. The launch procedure is `planning/AGENT_LAUNCH.md`.
