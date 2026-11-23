# Existing capability assessment

Assessed local instructions on 2026-11-16. Content hashes identify reviewed files even where upstream commits were unavailable. Local paths are discovery hints for this environment. Generated projects must resolve their own available source and version.

| Candidate | Reviewed SHA-256 | Reuse decision |
| --- | --- | --- |
| business-analyst | `147e6a8545583bd0ab73d6e214307799647f652c3eaa6732c7d2fb539dc3de6a` | Reuse for requirements elicitation when an interview is needed. The factory owns the approval and PlantUML handoff. |
| ux-designer | `1900a98c774e23573d20647c78819bbe0f1af5b0507d4254c89ff8966ce7e93a` | Reuse experience-design guidance. Add factory requirement links, PlantUML and the UX gate. |
| software-architect | `71e8d28e7c99f8b354ec11ddd71639c28899baa473d547c99ac26b035d05babd` | Reuse architecture analysis. Factory deployment targets, Terraform and human architecture approval apply. |
| orchestrator | `3b839885e621cab73d10e469b27567acbebb2351da5fb53b0c06792dd8fdba27` | Reuse issue decomposition. Use factory orchestration instructions for epics and execution; its queue/lease mechanics and labels are not adopted. |
| implementation-agent | `a5be429d5df75d67f4c57addc261aff68631f474a533e604b77a4812525fe0ff` | Reuse relevant delivery practices. Its mandatory image/development outcome and integration mechanisms must match actual project ACs and architecture. |
| review-agent | `3d8b6325b142cc5710b1850a60b80a6fde019f3f6271dda0d21c190371d75be4` | Reuse connected-code review. Factory QA recommendations lead to the human merge gate. |
| release-agent | `44b2351c9eeb5089e2e3997c98210b884c5288812cb9db49eda51bdea4abaf8c` | Existing instructions assume immutable images and a protected deployment approval workflow. The factory uses the approved project artifact design and recorded Codex production decision before main promotion. |
| monitoring-agent | `3514c218cce73bbbed42cb3301279c017437c7de0e356b33a50b507efafd0c0d` | Reuse evidence-based observations. Existing daily digests and notifications require project-specific authorization. |
| find-skills | `c00eeea0e13e74fe4a9d84ba0a8542205a1b736d65f13134fe1a6647eb14976f` | Reuse external candidate discovery, then review the actual source and version before invocation. |
| bigquery-basics | `6b137f7b9923d3a89465456d3f9ebdf73daec2f689b604593167686ad0f1777e` | A product administration capability. It does not supply general Terraform delivery procedures. |
| cloud-run-basics | `2636ca9682e587bfa302332d05b352110d6804cec489b31a2b603e4665c0ff6d` | A Cloud Run administration capability. It does not supply a target-neutral CI/CD or Terraform lifecycle. |

## CI/CD and Terraform

The available skill catalog contains Cloud Build, Cloud Run and Google Cloud architecture capabilities. Cloud Build guidance does not replace the required GitHub Actions design. The factory phase definitions, operating guide and SAD template cover CI/CD ownership, required checks, Terraform design and approval boundaries. A separate factory CI/CD or Terraform specialist would duplicate those instructions at this stage. Reassess tool-specific gaps when a project selects its stack and Terraform provider configuration.

Review candidates from find-skills or https://github.com/affaan-m/ecc when a concrete gap remains. Review license, source revision, dependencies, commands and required actions before use. No ECC skill has been imported or represented as assessed.

## Factory skill versions

The five factory skills are instruction-only implementations. Their catalog uses `git-commit` as a version policy. Resolve it to the actual pinned commit when invoking or recording use. The behavioral review cases and observations are in tests/skill-scenarios.md and docs/validation.md.
