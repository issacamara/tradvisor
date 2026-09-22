# V1 agent launch

The repo contains a paused local Codex launcher. It does not schedule background runs or change GitHub until `start` is invoked. Run from a terminal on the machine with authenticated Codex and GitHub CLI:

```sh
python3 planning/launch_agents.py check
python3 planning/launch_agents.py start
```

`check` reads the published backlog, current issue state, CLI authentication, branch, and local file status. `start` repeats those checks, then opens a Codex dispatcher session. The dispatcher uses `.codex/agents/implementation_agent.toml`, `review_agent.toml`, and `financial_advisor.toml`. It processes one implementation ticket at a time, creates a PR, obtains current-head CI and independent review, then merges and reevaluates dependencies. The launcher resumes with a fresh dispatcher session when an issue closes. It stops on an owner decision, a reported blocker, or two cycles without a closed ticket. Event metadata and structured result summaries go under ignored `.agent-runs/`; raw tool outputs are not logged there.

Codex uses its model's default automatic context compaction threshold. The dispatcher, financial advisor, reviewer, and first two implementation attempts for every ticket use `gpt-5.6-terra`. After two confirmed failed implementation attempts for the same ticket, its next implementation attempt uses `gpt-5.6-sol`. The reviewer remains on Terra. Inspect a choice with `python3 planning/model_policy.py V1-055`. Review uses high reasoning; initial implementation uses medium and escalated implementation uses high. The dispatcher passes the selected model explicitly when spawning agents. Model choice never relaxes CI or independent review.

The failure count lives in ignored `.agent-runs/ticket-failures.json`. A failed attempt means concluded code work with failing required tests or a REQUEST_CHANGES review. Interruptions and usage limits do not count. The dispatcher posts evidence on the ticket and records the attempt by PR head SHA, or by implementer session ID before a PR exists. `python3 planning/model_policy.py record-failure V1-055 ATTEMPT_ID` is idempotent. Keep this ledger with the Codex session store when moving the launcher to another machine; otherwise reconcile it from ticket checkpoints before resuming.

Recovery state is stored atomically in `.agent-runs/active.json` with the exact Codex session ID, cycle, model, process ID, and last verified closure set. Restarting `start` resumes that session when interrupted; it does not launch a second dispatcher or replay a completed result. Before any new GitHub write the dispatcher reconciles the issue, reservation, PR, CI, and V1 state. Ticket checkpoints are also posted to GitHub at reservation, PR, CI, review, and merge. The launcher does not store raw agent output in its metadata log.

Recognized usage-limit errors pause for 30 minutes, then resume the same session, up to 12 waits (six hours total). A longer limit or exhausted retry budget stops with the checkpoint intact; run `start` again after the limit resets. Other errors stop immediately with the same resumable checkpoint. If no session ID was captured, or an old Codex child may still be running, the launcher stops for inspection instead of risking duplicate work. Recovery needs the same machine and Codex session store; it is not a distributed failover mechanism.

The same local GitHub login is used by the agents. That is an accountable shared principal, not a separate reviewer identity. The dispatcher stops if branch protection requires a distinct approving GitHub account. The host must remain on and connected while the command runs; a stopped run can be restarted with `start` after inspecting the epic and the prior log. Do not run two dispatchers simultaneously. A completed, blocked, or decision-required checkpoint requires owner review before a new campaign; do not delete `.agent-runs/active.json` blindly.

The first code tickets are [#4](https://github.com/issacamara/tradvisor/issues/4) and [#6](https://github.com/issacamara/tradvisor/issues/6). [#3](https://github.com/issacamara/tradvisor/issues/3) and [#5](https://github.com/issacamara/tradvisor/issues/5) require real operator or legal-review evidence. Cloud changes, paid runs, development deployment, and release retain their separate approvals. No automatic deployment is configured.
