# Operating guide

## Shared phase contract

Identify the repository, request, owner, input versions and required outcome. Read the relevant agent definition and approved GitHub records. Discover specialist capabilities from `skills/catalog.yaml`, then local skills, `find-skills` or ECC when needed. Evaluate purpose, applicability, inputs, outputs, required actions, source and version. Review external instructions and licensing before reuse. Record selected skills and revisions in the relevant GitHub record. A phase owner integrates specialist results and records uncertainty and gaps.

Save reusable inputs in version-controlled files. Keep planning, delivery and decisions in their existing GitHub issue or PR when a separate file adds no value. Use requirement IDs such as BR-001 and UX-001. Use `ADR-001-short-title.md` for decisions and `.puml` for required UML sources. Other filenames and folders use lowercase hyphenated names, with platform filenames such as AGENTS.md, README.md and SKILL.md preserved.

## GitHub issue labels

Each GitHub issue has exactly one `phase:` label for its current accountable lifecycle owner, one `type:` label for the kind of work, and one implementation complexity label: `complexity:easy`, `complexity:medium`, or `complexity:hard`. Use `phase:intake`, `phase:business`, `phase:ux-ui`, `phase:architect`, `phase:orchestrator`, `phase:implementation`, `phase:qa`, `phase:release`, `phase:operations`, or `phase:defect-triage` for the owner. Use an appropriate work type such as `type:feature`, `type:bug`, or `type:maintenance`.

The issue creator applies these labels; the Orchestrator applies or updates them when creating or reassigning issues. Phase owners keep them accurate at handoffs and as the work changes, replacing outdated labels within each family. Labels support filtering and routing; issue content and linked records remain authoritative for scope, dependencies, approvals and completion. An optional `lane:fast` label marks a fast-lane issue as described under Epic and issue delivery. The project's issue-labels workflow runs `scripts/check_labels.py` on every issue change and fails when these rules are broken.

## Skill selection and execution

The active Codex session assumes the role in `agents/sf-<phase>-agent.md`. That phase owner selects skills according to the task and follows their instructions using the session's available tools. The filename identifies the phase role, and the skill's SKILL.md supplies the specialist procedure.

1. Search the project's `skills/catalog.yaml` for the needed capability. Read purpose, when_to_use, keywords, required inputs and outputs. Resolve the selected instructions relative to the project's `skills/` directory. For example, `test-strategy-design/SKILL.md` resolves to `skills/test-strategy-design/SKILL.md` in this project.
2. Inspect project-local skills and the host's available skill list for suitable existing capabilities. Repository-local discovery uses `.agents/skills/` for Codex and `.claude/skills/` for Claude Code. Factory skills are included in `skills/`, `.agents/skills/` and `.claude/skills/`. Keep all copies aligned when updating them. Installed skills outside the repository are read from the actual paths supplied by the host, including user-configured skill locations.
3. If a capability gap remains, use an available `find-skills` skill or inspect candidates such as ECC. Read the candidate's actual SKILL.md and relevant referenced resources. Check its purpose, compatibility, inputs, outputs, source version, license, dependencies, available tools and required actions against the task. Read an accessible compatible skill directly, or install/register it when the task needs that and existing authorization covers the action.
4. Supply the selected skill with the phase's task, approved input versions, scope, constraints and expected result. Read its SKILL.md and follow the relevant procedure. Load supporting references when that procedure needs them, and run scripts or tools when the skill and task call for them. A discovered skill can be invoked by its host name, such as `$factory-test-strategy-design`. An accessible skill can also be used by explicitly instructing Codex to read its path and apply it.
5. Review the result against the phase's acceptance criteria. Record the skill name, source path or URL, exact commit/release version, supplied inputs, result, limits and the owner's integration decision in the relevant GitHub issue or PR. Resolve the catalog's `git-commit` marker to the factory SHA recorded in `.factory.json`. For a local skill without upstream version metadata, record the reviewed content hash and the missing upstream version explicitly.
6. If the required capability or tool is unavailable, record the concrete gap and whether it prevents the outcome. Continue independent authorized work and route a blocking gap through intake or the responsible owner. Filling a gap does not transfer accountability away from the phase owner.

For example, `sf-architect-agent` can select the factory test-strategy skill for acceptance coverage and an installed cloud-specific skill for infrastructure design. It supplies both with the approved BRD, UX and deployment constraints, then integrates their recommendations into the SAD. `sf-business-agent` can use an installed business-analysis skill for stakeholder elicitation through the same procedure. Use `templates/specialist-result.md` when the result needs a reusable record.

## UML visuals

Each `.puml` diagram should have an Archify visual when the Archify skill is available. Use the PlantUML source as the authority and translate its actors, elements, relationships and behavior into Archify JSON. Use workflow for use cases and activities, architecture for component, class and deployment diagrams, sequence for interactions, and lifecycle for state machines. Check that the visual preserves the source's meaning, including labels, branches and relationship types. Report any source semantics that the chosen mode cannot represent faithfully.

For a source named `example.puml`, save `example.archify.json`, `example.archify.html` and the Archify receipts and other generated files in the source directory. Use the final HTML path in the candidate's output metadata and follow the installed Archify skill's `finalize` procedure, directing output and evidence to that same directory. If one file defines multiple diagrams, use a distinct suffix for each diagram's outputs. Link each HTML visual and its passing receipt from the phase artifact or GitHub record.

The phase owner delivers the source and visual together for review, regenerates the visual and evidence whenever the source changes, and moves or removes the companion files with the source. QA checks affected sources against their companion visuals and passing receipts. When Archify is unavailable, deliver the PlantUML source alone and record the missing visual as a known gap in the phase record; the gap does not block approval. A produced visual that misrepresents its source or fails finalization is a defect to fix before review.

## Lifecycle and approvals

| Owner | Inputs and outcome | Next gate or handoff |
| --- | --- | --- |
| Intake | Request to classification, skill gaps and routing | Human approves intake and skill-gap decision, then Intake merges the intake-only PR before Business |
| Business | Approved intake to requirements, ACs, KPIs and business models | Human approves requirements |
| UX/UI | Approved BRD to journeys, screens, states and UI criteria | Human approves UX/UI |
| Architect | Approved BRD and UX to SAD, contracts, ADRs, tests and deployment design | Human approves architecture |
| Orchestrator | Approved inputs to epics, linked child issues and dependency graphs | Ready issues to Implementation, integrated epic PR to QA, confirmed development merge to Release |
| Implementation | One issue to verified changes and a PR into its epic | QA, human approval and confirmed epic merge before cleanup |
| QA | Issue or epic PR, ACs and CI to quality recommendation | Human approves merging the reviewed PR head |
| Release | Confirmed development merge to verified deployment, then production PR into main | Human approves production promotion of that PR head |
| Operations | Deployed versions and telemetry to findings and improvements | Intake or defect triage |
| Defect triage | Evidence to reproducible, prioritized work | Orchestration and relevant phase owners |

For an approved idea, Intake commits the approved intake record, opens an intake-only PR into development, and merges it after required checks and branch rules pass. The recorded intake decision authorizes this merge without a separate human merge decision. Link the approved version and decision in the PR, record the merge commit, and hand the merged record to Business. Material changes to the approved intake require a renewed intake decision. Branch rules remain authoritative; if they require a separate review, record the blocker and do not bypass them. This exception does not authorize implementation, setup, promotion, or other changes.

The normal flow is intake → business → UX/UI → architecture → orchestration → issue PRs into the epic → epic PR into development → verified development deployment → production PR into main → verified production deployment → operations. Issue, epic and production PRs each have their own verification and human approval. Revisions return to the responsible owner. Defects enter triage, and priority changes execution order while retaining verification and approvals.

Before an approved step, read the actual decision from GitHub and compare the approved artifact commit or PR head with the current item. Check conditions and required evidence. Missing, stale or conditional approval leaves that step pending. A material change requires a renewed decision. Except for the intake-only PR above, approval of a project phase does not approve later merges or production promotion. Use `templates/human-decision.md` to record an actual Codex decision, including date, timezone, identity and source link where available. A comment is an agent-checked decision record. Native GitHub reviews have their own meaning and remain subject to configured branch rules.

Immediately before any merge or production promotion, run `python scripts/check_gate.py <pr> --gate merge` (or `--gate production`), adding `--approver <login>` for each person allowed to decide. It passes only when the latest decision record or native review for the current PR head approves it without open conditions. A nonzero exit leaves the step pending.

For a small request the human may approve adjacent phases, such as intake with business or UX/UI with architecture, in one decision record that names every approved artifact version. Each artifact is still produced and reviewed; only the number of decision rounds shrinks.

## Repository work and bootstrap

For existing repositories, fetch the approved remote base and use a dedicated worktree. Implementation issues use detached worktrees as described below. Other repository changes use a dedicated branch when needed. Read relevant source, callers and records, make the scoped change, verify acceptance, commit, push and open or update its PR. Read-only repository assessments also use a worktree when inspecting versioned inputs. GitHub-record-only or display-only tasks need none.

After a same-repository pull request is merged into `development`, delete its source branch on GitHub and locally after confirming the merge, preserving any unmerged work and checking that no open pull request still uses it as head or base. Never delete `main` or `development`. The cleanup workflow runs only for merged pull requests into `development`; it skips branches that advanced or remain in use and uses a lease so a concurrent update cannot be deleted. A phase owner verifies the outcome and performs safe cleanup if the workflow is unavailable, skipped or fails. Until the workflow is present on the default branch, including project bootstrap, perform that cleanup directly. Fork branches and branches with unmerged work remain with their owners. Remove the completed worktree only after its work and evidence are safe; never remove another task’s worktree.

For the first factory or project repository, initialize Git with an empty bootstrap commit so worktrees and branches can exist. Record bootstrap as setup work and place substantive changes on a dedicated branch for review. The first project setup PR can target development. Establish main, development and protection settings before relying on normal delivery. A blocked or incomplete task retains its worktree until safely recorded or the human directs otherwise.

## Epic and issue delivery

### Plan the epic

Orchestration groups related issues under a GitHub tracking issue. Record the required issue list, dependency order, owners, combined acceptance criteria and starting development SHA. Fetch `origin/development` and create and publish one `epic/<epic-number>` branch from that tip. Check the tracking record and remote before creating the branch so retries reuse the same branch. Where an issue depends on code in another epic, wait for that code to reach development and bring it into the dependent epic before assigning the issue.

### Merge each issue into its epic

1. Fetch the assigned remote epic branch. Create a dedicated worktree with `git worktree add --detach <path> origin/epic/<epic-number>`. Commit in that worktree and push with `git push origin HEAD:refs/heads/issue/<issue-number>`. This creates the temporary remote branch without creating a local issue branch. Use that remote branch as the PR head and the assigned epic branch as the base. Record the PR on the issue.
2. Run required checks and issue QA, then obtain and record human merge approval for the current PR head. Recheck the reviewed head and base and enforce the approved head at merge time, for example with `gh pr merge --match-head-commit <approved-head-sha>`. Follow the configured branch rules. If the PR cannot merge, keep the detached worktree, temporary branch and same PR. Resume in the existing worktree. Update the issue and PR with the blocker. When the epic has moved, fetch it and incorporate the new base in the detached worktree as needed. Resolve the blocker, update the same remote branch and PR as needed, then repeat required checks, QA and human approval before retrying.
3. After GitHub confirms the PR merged into the assigned epic, record the merge commit and final PR head. Remove the owned worktree normally once it is clean and its detached HEAD matches the merged PR head. Delete the temporary remote ref once it is unused by open PRs and still at the merged PR head. Use `git push --force-with-lease=refs/heads/issue/<issue-number>:<merged-head-sha> origin :refs/heads/issue/<issue-number>` to protect concurrent changes. Treat an already absent branch as cleaned up. Retain dirty worktrees or advanced branches and record any cleanup still pending. If deployment evidence is part of the issue's acceptance criteria, track it through the epic.

### Promote the epic to development

1. Once GitHub confirms every required issue PR merged into the epic, Orchestration opens one PR from the epic branch into `development`. Link the epic record and the merged issue PRs. Run required CI and combined QA against the current PR head and development base, including integration and regression checks. Obtain a separate human merge approval for the epic PR head.
2. If promotion is blocked, keep the epic branch and reuse the open PR. Resolve merge conflicts on the epic branch by merging the latest development tip into it in a dedicated worktree and pushing the resolution without rewriting the epic history. Add each regression fix to the epic's required issues and deliver it through a linked issue PR into the same epic using the issue workflow above. After any blocker is resolved, refresh the PR evidence, repeat required checks and combined QA, and obtain fresh human approval before retrying the epic merge. Apply the same head, base and branch-rule checks used for issue PRs.
3. Confirm the merge in GitHub, record the development merge commit, and verify source-branch cleanup under the repository policy above. Release verifies the development deployment for that merge commit through the approved workflow and links the result to the epic. If the deployment fails, follow the project's recovery procedure and keep the epic pending until development is verified.

### Fast lane

Orchestration may add `lane:fast` to an issue only when every condition holds: it is labeled `complexity:easy`; it changes no approved requirement, contract, schema, data migration, security boundary, deployment or infrastructure; and it depends on no unmerged work. A fast-lane issue needs no epic. Implementation creates a detached worktree from `origin/development`, pushes to `issue/<issue-number>` and opens one PR into `development`. Required checks, QA and an exact-head human merge decision still apply, and that one decision replaces the separate issue and epic approvals. Release verifies the development deployment as for an epic merge. If the work grows beyond these limits, remove `lane:fast`, record why and move the issue into an epic before merging.

## Evidence and completion

Use `templates/acceptance-evidence.md` to record a result and evidence for each AC. Manual checks identify the performer, environment or artifact version and observation. Missing or failed evidence remains incomplete. Implementation changes require passing tests, lint, build and security scanning for the candidate being delivered. Record the head SHA and relevant target base. Refresh changed inputs and rerun affected checks when the candidate changes.

Link requirement or approved artifact → issue → PR → CI and acceptance evidence → release or deployment → defect when relevant. GitHub links provide traceability. An implementation issue can complete at its confirmed epic merge if its acceptance criteria are satisfied. An issue with deployment criteria stays pending until the required environment is verified. Record issue completion explicitly in GitHub and use merged PR evidence to determine whether the epic can proceed. Apply the issue cleanup rules above after an epic merge. For other tasks, confirm required changes and records are safely preserved, approvals are recorded and outcomes are verified before removing an owned worktree. Never remove another task's changes.

## Development and production

GitHub Actions provides tests, lint, build and security scanning. Every generated project must implement real stack-specific checks after architecture approval. Required check names and branch rules must match actual jobs. Run PR checks for both `epic/*` and `development` targets. For a documentation-only bootstrap, verify generated content and instructions with applicable checks and clearly record application checks awaiting architecture.

Except for the intake-only PR described above, merge a PR into development only after the human decision applies to its current head and checks pass. Record the merge commit and verify development using the approved project workflow. Prepare a production promotion PR from development into main with the artifact identity, configuration, verification, migration and rollback evidence. Obtain and record human production approval against that PR head before merging into main. The push triggers the project's production workflow. Verify the deployed version and release outcome. A failed deployment invokes the approved project failure and recovery procedure.

Architecture chooses the stack, artifact identity, deployment mechanism, environment separation, observation criteria and rollback. Use an immutable artifact identity where the chosen delivery mechanism supports one. Cloud deployment requires Terraform, with state storage, access, locking, credentials, plan review, apply, verification and recovery defined by the project. Terraform follows the same approval rules. Local projects define how both development and production are hosted and separated on their local target.

## Defects and emergencies

Record detection source, affected version and environment, expected and actual behavior, impact, severity, priority, reproduction or its current blocker, and evidence. Create a failing regression test when testable. Link the fix PR, checks, QA, deployed version and verification. Keep unproven causes labeled as hypotheses. Critical, recurring or security-related defects invoke RCA / Prevention when proportionate. A fix is closed with deployment evidence when deployment is part of the defect's completion criteria.

For an emergency, branch from main in a dedicated worktree, implement the smallest fix and regression test, and open a PR into main. Run required checks and QA. Obtain a human production decision for the exact hotfix head, which covers merging that specific PR into main. Deploy and verify, using documented rollback on failure. Open a linked follow-up PR into development so future promotion preserves the fix. That PR needs its own merge decision and checks. A failed required check or unverifiable fix keeps the release pending.

## Maintain the factory

Record factory changes through the same issue and PR evidence. Refresh external skill assessments when versions change. Tag an approved, merged and validated factory commit for generation. New projects record that source revision. Existing projects adopt a new revision through a reviewed change to provenance, reconciling changed instructions and templates before use.
