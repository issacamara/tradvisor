<!-- tradvisor-v1-tracking-epic -->
## Scope And Authority
Approved sanitized baseline: BASELINE_PENDING. Target integration branch: `V1`.
Seven responsibilities: reused Ingestion, Analytical Data and Pipeline Orchestration; new Analysis Engine, Investor Application, Paper Trading and Application Store.
Deliver Swing (EMA20/50, RSI14, ATR14, liquidity and versioned entry/exit rules), equal-priority Long-Term Growth/dividend research, and manual recommendation-linked paper trading with reset/recovery protection.
Static Next.js/TypeScript frontend, FastAPI, shared batch analysis, structured Firestore and existing cloud ingestion foundation. No Dividend/Balanced composite scores or real portfolio tracking in V1.

## Governance
This epic is the scheduling source of truth. No agents are assigned or dispatched. No roster/identity mapping has been established; do not fabricate one. All tickets retain `blocked` while dispatch is disabled, even where `Blocked by: none` means there is no technical predecessor. After graph publication is reconciled, a later explicitly authorized dispatch can evaluate eligibility and change labels.
One active dispatcher, one ticket per agent; reserve the actual agent and file ownership here before dispatch. Re-read issue/PR state and verify predecessor artifacts merged into V1. A closed/cancelled issue or a wave number is not proof of delivery. Recompute conflicts if scope/files change. Agent tasks are not launched by adding an assignee alone.
Existing user work must be preserved. Use the original restricted operator evidence for real environment targeting. This public epic contains no environment inventory or credentials. No production cloning/writes, destructive migration, paid run, plan/apply, seed, or schedule activation is authorized by backlog publication. Deployment and release approvals remain separate.
Estimates: S: up to 2 hours; M: 2-4 hours. Split before implementation if scope exceeds half a day. Re-split oversized work before assigning; external evidence/approval wait is not implementation time. Review-only tasks require the named role's evidence, not invented sign-off. No milestones or delivery-date promises have been introduced.

## Validation
77 tickets, 17 waves, 38 undirected file-conflict pairs. Required fields, acyclic hard-dependency graph, reverse edges, one wave per ticket, predecessors in earlier waves, conflict-free waves and every ticket's path to final release are validated locally. Public safety scans exclude private paths, environment IDs and inventory. Live publication verification is recorded separately; document checks are not passing application tests.

## Tickets And Estimates
| Wave | Ticket | Estimate | Domain |
|---|---|---|---|
| 1 | V1-006 Verify development ownership and preservation inputs | M | infrastructure |
| 1 | V1-055 Build the responsive static investor workspace shell | M | frontend |
| 1 | V1-073 Record legal privacy and advisory release review | S | operations |
| 1 | V1-075 Establish isolated Python package and fixture test foundations | S | contracts |
| 2 | V1-001 Define exact-money scalars and command envelopes | M | contracts |
| 2 | V1-007 Preserve existing Terraform resource ownership | M | infrastructure |
| 3 | V1-002 Define analytical input and result schemas | M | contracts |
| 3 | V1-008 Review the complete preservation-only Terraform plan | S | infrastructure |
| 3 | V1-044 Implement exact paper cost and P&L arithmetic | M | paper |
| 4 | V1-003 Define transactional paper and REST schemas | M | contracts |
| 4 | V1-009 Preserve retry-stable raw ingestion evidence | M | ingestion |
| 4 | V1-024 Define additive analytical source and revision structures | M | infrastructure |
| 4 | V1-029 Build point-in-time analytical session inputs | M | analysis |
| 5 | V1-004 Generate the versioned OpenAPI and TypeScript client | M | contracts |
| 5 | V1-010 Make shared BigQuery loads idempotent and isolated | M | ingestion |
| 5 | V1-025 Configure static hosting and invited identity foundation | M | infrastructure |
| 5 | V1-030 Implement seeded EMA20 and EMA50 with replay anchors | M | analysis |
| 5 | V1-031 Implement Wilder RSI14 and interruption handling | M | analysis |
| 5 | V1-032 Implement Wilder ATR14 with labeled no-trade modeling | M | analysis |
| 5 | V1-033 Calculate complete-window liquidity eligibility | M | analysis |
| 5 | V1-035 Calculate Growth activity and profitability dimensions | M | analysis |
| 5 | V1-036 Calculate sector resilience and valuation dimensions | M | analysis |
| 5 | V1-038 Publish supported dividend facts without composite scores | M | analysis |
| 5 | V1-040 Implement versioned Firestore repositories and transaction seams | M | backend |
| 5 | V1-050 Implement ordered independent recovery-register operations | M | backend |
| 6 | V1-005 Extend CI with isolated contract and application checks | M | ci |
| 6 | V1-011 Normalize issuer identity and financial category evidence | M | ingestion |
| 6 | V1-012 Implement versioned exchange calendar ingestion | M | ingestion |
| 6 | V1-014 Align existing financial PDF extraction entry points | M | ingestion |
| 6 | V1-026 Configure scale-to-zero API and bounded jobs | M | infrastructure |
| 6 | V1-034 Implement the versioned trend-confirmation strategy | M | analysis |
| 6 | V1-037 Compose Growth ratings and independent advisory guards | M | analysis |
| 6 | V1-041 Enforce verified identity and current invitation admission | M | backend |
| 6 | V1-042 Implement recovery-fenced idempotency receipts | M | backend |
| 6 | V1-056 Build sign-in verification and password-reset flows | M | frontend |
| 6 | V1-057 Build the Swing screener and indicator detail | M | frontend |
| 6 | V1-058 Build Growth rankings and first-class dividend research | M | frontend |
| 6 | V1-059 Build paper portfolio reporting and order history | M | frontend |
| 7 | V1-013 Normalize genuine share observations and source sessions | M | ingestion |
| 7 | V1-015 Normalize annual reporting and non-financial inputs | M | ingestion |
| 7 | V1-018 Normalize matching ordinary capitalization evidence | M | ingestion |
| 7 | V1-019 Normalize supported price and share adjustment evidence | M | ingestion |
| 7 | V1-020 Normalize existing dividend payments and coverage | M | ingestion |
| 7 | V1-021 Normalize rating-specific history and loading | M | ingestion |
| 7 | V1-027 Configure transactional storage and protected recovery storage | M | infrastructure |
| 7 | V1-039 Persist immutable analytical batches and readiness manifests | M | analysis |
| 7 | V1-043 Implement paper setup and versioned preferences | M | paper |
| 7 | V1-045 Implement versioned position exit advice | M | paper |
| 7 | V1-052 Implement recovery-safe trusted admission changes | M | backend |
| 7 | V1-060 Implement confirmed paper commands and uncertain-response handling | M | frontend |
| 8 | V1-016 Normalize evidenced banking activity and capital inputs | M | ingestion |
| 8 | V1-017 Normalize evidenced insurance activity and solvency inputs | M | ingestion |
| 8 | V1-046 Publish transactionally guarded execution-price revisions | M | backend |
| 8 | V1-047 Publish complete immutable analytical serving copies | M | backend |
| 9 | V1-022 Package reused ingestion functions with explicit settings | M | infrastructure |
| 9 | V1-048 Accept fresh manual orders with atomic reservations | M | paper |
| 10 | V1-023 Define explicit ingestion workflow dependencies | M | infrastructure |
| 10 | V1-049 Execute or expire pending orders exactly once | M | paper |
| 11 | V1-028 Restore approval-gated development delivery automation | M | ci |
| 11 | V1-051 Implement restrictive-intent-first portfolio reset | M | paper |
| 11 | V1-076 Persist session-ordered position exit references | M | paper |
| 12 | V1-053 Implement bounded authenticated analysis and paper reads | M | backend |
| 12 | V1-062 Integrate source readiness and daily publication | M | analysis |
| 12 | V1-063 Implement evidence-aware retention and reset cleanup | M | backend |
| 12 | V1-064 Implement isolated restore reconciliation and recovery fencing | M | backend |
| 13 | V1-054 Wire protected REST handlers and internal worker entry points | M | backend |
| 13 | V1-069 Review actual source and company-sector coverage | M | qa |
| 14 | V1-061 Connect all static workspaces to the protected API | M | frontend |
| 14 | V1-065 Add bounded operational telemetry and backup alerts | M | operations |
| 14 | V1-066 Verify cross-store and financial mutation races | M | qa |
| 14 | V1-068 Measure pilot latency and calculation placement costs | M | qa |
| 15 | V1-067 Verify complete workflows against WCAG 2.2 AA | M | qa |
| 15 | V1-070 Evaluate provisional financial rules on point-in-time holdouts | M | qa |
| 15 | V1-071 Validate the isolated backup and restore runbook | M | operations |
| 15 | V1-077 Configure bounded operational alerts and log retention | M | infrastructure |
| 16 | V1-072 Review measured whole-stack pilot operating cost | S | operations |
| 17 | V1-074 Assemble pilot acceptance and separate activation approvals | S | operations |

## Wave Plan
| Wave | Tickets | Parallelizability | Rationale |
|---|---|---|---|
| 1 | V1-006 (number pending), V1-055 (number pending), V1-073 (number pending), V1-075 (number pending) | May run concurrently after eligibility verification; no shared-file conflicts within this wave | All hard prerequisites are in earlier waves; conflicting owners are serialized |
| 2 | V1-001 (number pending), V1-007 (number pending) | May run concurrently after eligibility verification; no shared-file conflicts within this wave | All hard prerequisites are in earlier waves; conflicting owners are serialized |
| 3 | V1-002 (number pending), V1-008 (number pending), V1-044 (number pending) | May run concurrently after eligibility verification; no shared-file conflicts within this wave | All hard prerequisites are in earlier waves; conflicting owners are serialized |
| 4 | V1-003 (number pending), V1-009 (number pending), V1-024 (number pending), V1-029 (number pending) | May run concurrently after eligibility verification; no shared-file conflicts within this wave | All hard prerequisites are in earlier waves; conflicting owners are serialized |
| 5 | V1-025 (number pending), V1-004 (number pending), V1-010 (number pending), V1-030 (number pending), V1-031 (number pending), V1-032 (number pending), V1-033 (number pending), V1-035 (number pending), V1-036 (number pending), V1-038 (number pending), V1-040 (number pending), V1-050 (number pending) | May run concurrently after eligibility verification; no shared-file conflicts within this wave | All hard prerequisites are in earlier waves; conflicting owners are serialized |
| 6 | V1-026 (number pending), V1-005 (number pending), V1-011 (number pending), V1-012 (number pending), V1-014 (number pending), V1-034 (number pending), V1-037 (number pending), V1-041 (number pending), V1-042 (number pending), V1-056 (number pending), V1-057 (number pending), V1-058 (number pending), V1-059 (number pending) | May run concurrently after eligibility verification; no shared-file conflicts within this wave | All hard prerequisites are in earlier waves; conflicting owners are serialized |
| 7 | V1-027 (number pending), V1-013 (number pending), V1-015 (number pending), V1-018 (number pending), V1-019 (number pending), V1-020 (number pending), V1-021 (number pending), V1-039 (number pending), V1-043 (number pending), V1-045 (number pending), V1-052 (number pending), V1-060 (number pending) | May run concurrently after eligibility verification; no shared-file conflicts within this wave | All hard prerequisites are in earlier waves; conflicting owners are serialized |
| 8 | V1-016 (number pending), V1-017 (number pending), V1-046 (number pending), V1-047 (number pending) | May run concurrently after eligibility verification; no shared-file conflicts within this wave | All hard prerequisites are in earlier waves; conflicting owners are serialized |
| 9 | V1-022 (number pending), V1-048 (number pending) | May run concurrently after eligibility verification; no shared-file conflicts within this wave | All hard prerequisites are in earlier waves; conflicting owners are serialized |
| 10 | V1-023 (number pending), V1-049 (number pending) | May run concurrently after eligibility verification; no shared-file conflicts within this wave | All hard prerequisites are in earlier waves; conflicting owners are serialized |
| 11 | V1-028 (number pending), V1-051 (number pending), V1-076 (number pending) | May run concurrently after eligibility verification; no shared-file conflicts within this wave | All hard prerequisites are in earlier waves; conflicting owners are serialized |
| 12 | V1-053 (number pending), V1-062 (number pending), V1-063 (number pending), V1-064 (number pending) | May run concurrently after eligibility verification; no shared-file conflicts within this wave | All hard prerequisites are in earlier waves; conflicting owners are serialized |
| 13 | V1-054 (number pending), V1-069 (number pending) | May run concurrently after eligibility verification; no shared-file conflicts within this wave | All hard prerequisites are in earlier waves; conflicting owners are serialized |
| 14 | V1-061 (number pending), V1-065 (number pending), V1-066 (number pending), V1-068 (number pending) | May run concurrently after eligibility verification; no shared-file conflicts within this wave | All hard prerequisites are in earlier waves; conflicting owners are serialized |
| 15 | V1-067 (number pending), V1-070 (number pending), V1-071 (number pending), V1-077 (number pending) | May run concurrently after eligibility verification; no shared-file conflicts within this wave | All hard prerequisites are in earlier waves; conflicting owners are serialized |
| 16 | V1-072 (number pending) | Single task | All hard prerequisites are in earlier waves; conflicting owners are serialized |
| 17 | V1-074 (number pending) | Single task | All hard prerequisites are in earlier waves; conflicting owners are serialized |

## Dependency Graph
Solid arrows are hard prerequisites. Dotted undirected edges are file-conflict exclusions, not dependencies. Node IDs map to the ticket table; wave planning does not replace current ownership checks.
```mermaid
flowchart TD
  V1006["V1-006 "]
  V1055["V1-055 "]
  V1073["V1-073 "]
  V1075["V1-075 "]
  V1001["V1-001 "]
  V1007["V1-007 "]
  V1002["V1-002 "]
  V1008["V1-008 "]
  V1044["V1-044 "]
  V1003["V1-003 "]
  V1009["V1-009 "]
  V1024["V1-024 "]
  V1025["V1-025 "]
  V1026["V1-026 "]
  V1029["V1-029 "]
  V1004["V1-004 "]
  V1010["V1-010 "]
  V1027["V1-027 "]
  V1030["V1-030 "]
  V1031["V1-031 "]
  V1032["V1-032 "]
  V1033["V1-033 "]
  V1035["V1-035 "]
  V1036["V1-036 "]
  V1038["V1-038 "]
  V1040["V1-040 "]
  V1050["V1-050 "]
  V1005["V1-005 "]
  V1011["V1-011 "]
  V1012["V1-012 "]
  V1014["V1-014 "]
  V1034["V1-034 "]
  V1037["V1-037 "]
  V1041["V1-041 "]
  V1042["V1-042 "]
  V1056["V1-056 "]
  V1057["V1-057 "]
  V1058["V1-058 "]
  V1059["V1-059 "]
  V1013["V1-013 "]
  V1015["V1-015 "]
  V1018["V1-018 "]
  V1019["V1-019 "]
  V1020["V1-020 "]
  V1021["V1-021 "]
  V1039["V1-039 "]
  V1043["V1-043 "]
  V1045["V1-045 "]
  V1052["V1-052 "]
  V1060["V1-060 "]
  V1016["V1-016 "]
  V1017["V1-017 "]
  V1046["V1-046 "]
  V1047["V1-047 "]
  V1022["V1-022 "]
  V1048["V1-048 "]
  V1023["V1-023 "]
  V1049["V1-049 "]
  V1028["V1-028 "]
  V1051["V1-051 "]
  V1076["V1-076 "]
  V1053["V1-053 "]
  V1062["V1-062 "]
  V1063["V1-063 "]
  V1064["V1-064 "]
  V1054["V1-054 "]
  V1069["V1-069 "]
  V1061["V1-061 "]
  V1065["V1-065 "]
  V1066["V1-066 "]
  V1068["V1-068 "]
  V1067["V1-067 "]
  V1070["V1-070 "]
  V1071["V1-071 "]
  V1077["V1-077 "]
  V1072["V1-072 "]
  V1074["V1-074 "]
  V1075 --> V1001
  V1006 --> V1007
  V1001 --> V1002
  V1007 --> V1008
  V1001 --> V1044
  V1001 --> V1003
  V1002 --> V1003
  V1002 --> V1009
  V1008 --> V1024
  V1002 --> V1024
  V1008 --> V1025
  V1008 --> V1026
  V1002 --> V1029
  V1003 --> V1004
  V1055 --> V1004
  V1009 --> V1010
  V1008 --> V1027
  V1003 --> V1027
  V1029 --> V1030
  V1029 --> V1031
  V1029 --> V1032
  V1029 --> V1033
  V1029 --> V1035
  V1029 --> V1036
  V1029 --> V1038
  V1003 --> V1040
  V1003 --> V1050
  V1004 --> V1005
  V1010 --> V1011
  V1010 --> V1012
  V1010 --> V1014
  V1030 --> V1034
  V1031 --> V1034
  V1032 --> V1034
  V1033 --> V1034
  V1035 --> V1037
  V1036 --> V1037
  V1040 --> V1041
  V1040 --> V1042
  V1055 --> V1056
  V1004 --> V1056
  V1055 --> V1057
  V1004 --> V1057
  V1055 --> V1058
  V1004 --> V1058
  V1055 --> V1059
  V1004 --> V1059
  V1011 --> V1013
  V1012 --> V1013
  V1014 --> V1015
  V1011 --> V1015
  V1011 --> V1018
  V1010 --> V1018
  V1011 --> V1019
  V1010 --> V1019
  V1011 --> V1020
  V1010 --> V1020
  V1011 --> V1021
  V1010 --> V1021
  V1034 --> V1039
  V1037 --> V1039
  V1038 --> V1039
  V1041 --> V1043
  V1042 --> V1043
  V1044 --> V1045
  V1034 --> V1045
  V1003 --> V1045
  V1041 --> V1052
  V1050 --> V1052
  V1056 --> V1060
  V1059 --> V1060
  V1057 --> V1060
  V1015 --> V1016
  V1015 --> V1017
  V1040 --> V1046
  V1012 --> V1046
  V1013 --> V1046
  V1040 --> V1047
  V1039 --> V1047
  V1008 --> V1022
  V1013 --> V1022
  V1015 --> V1022
  V1016 --> V1022
  V1017 --> V1022
  V1020 --> V1022
  V1021 --> V1022
  V1043 --> V1048
  V1045 --> V1048
  V1047 --> V1048
  V1046 --> V1048
  V1022 --> V1023
  V1048 --> V1049
  V1044 --> V1049
  V1005 --> V1028
  V1023 --> V1028
  V1024 --> V1028
  V1025 --> V1028
  V1026 --> V1028
  V1027 --> V1028
  V1043 --> V1051
  V1050 --> V1051
  V1049 --> V1051
  V1045 --> V1076
  V1049 --> V1076
  V1040 --> V1076
  V1041 --> V1053
  V1047 --> V1053
  V1045 --> V1053
  V1049 --> V1053
  V1076 --> V1053
  V1023 --> V1062
  V1024 --> V1062
  V1013 --> V1062
  V1016 --> V1062
  V1017 --> V1062
  V1018 --> V1062
  V1019 --> V1062
  V1020 --> V1062
  V1021 --> V1062
  V1047 --> V1062
  V1046 --> V1062
  V1076 --> V1062
  V1051 --> V1063
  V1047 --> V1063
  V1050 --> V1063
  V1051 --> V1064
  V1052 --> V1064
  V1049 --> V1064
  V1047 --> V1064
  V1053 --> V1054
  V1051 --> V1054
  V1052 --> V1054
  V1062 --> V1069
  V1054 --> V1061
  V1057 --> V1061
  V1058 --> V1061
  V1060 --> V1061
  V1054 --> V1065
  V1062 --> V1065
  V1063 --> V1065
  V1054 --> V1066
  V1064 --> V1066
  V1063 --> V1066
  V1062 --> V1066
  V1062 --> V1068
  V1054 --> V1068
  V1061 --> V1067
  V1062 --> V1070
  V1068 --> V1070
  V1069 --> V1070
  V1064 --> V1071
  V1066 --> V1071
  V1027 --> V1071
  V1028 --> V1071
  V1065 --> V1077
  V1027 --> V1077
  V1026 --> V1077
  V1068 --> V1072
  V1071 --> V1072
  V1065 --> V1072
  V1028 --> V1074
  V1061 --> V1074
  V1062 --> V1074
  V1066 --> V1074
  V1067 --> V1074
  V1069 --> V1074
  V1070 --> V1074
  V1072 --> V1074
  V1073 --> V1074
  V1077 --> V1074
  V1004 -.- V1055
  V1005 -.- V1055
  V1006 -.- V1008
  V1007 -.- V1022
  V1007 -.- V1023
  V1007 -.- V1024
  V1007 -.- V1025
  V1007 -.- V1026
  V1007 -.- V1027
  V1007 -.- V1077
  V1009 -.- V1010
  V1022 -.- V1023
  V1022 -.- V1024
  V1022 -.- V1025
  V1022 -.- V1026
  V1022 -.- V1027
  V1022 -.- V1077
  V1023 -.- V1024
  V1023 -.- V1025
  V1023 -.- V1026
  V1023 -.- V1027
  V1023 -.- V1077
  V1024 -.- V1025
  V1024 -.- V1026
  V1024 -.- V1027
  V1024 -.- V1077
  V1025 -.- V1026
  V1025 -.- V1027
  V1025 -.- V1077
  V1026 -.- V1027
  V1026 -.- V1077
  V1027 -.- V1077
  V1055 -.- V1056
  V1055 -.- V1057
  V1055 -.- V1058
  V1055 -.- V1059
  V1055 -.- V1060
  V1055 -.- V1061
```

## Conflict Register
| Ticket | Conflicts With | Overlapping Files/Modules |
|---|---|---|
| V1-004 (number pending) | V1-055 (number pending) | `frontend/` |
| V1-005 (number pending) | V1-055 (number pending) | `frontend/` |
| V1-006 (number pending) | V1-008 (number pending) | `operator-evidence/infrastructure/` |
| V1-007 (number pending) | V1-022 (number pending) | `terraform/` |
| V1-007 (number pending) | V1-023 (number pending) | `terraform/` |
| V1-007 (number pending) | V1-024 (number pending) | `terraform/` |
| V1-007 (number pending) | V1-025 (number pending) | `terraform/` |
| V1-007 (number pending) | V1-026 (number pending) | `terraform/` |
| V1-007 (number pending) | V1-027 (number pending) | `terraform/` |
| V1-007 (number pending) | V1-077 (number pending) | `terraform/` |
| V1-009 (number pending) | V1-010 (number pending) | `archive/legacy-ingestion/scripts/helper.py` |
| V1-022 (number pending) | V1-023 (number pending) | `terraform/` |
| V1-022 (number pending) | V1-024 (number pending) | `terraform/` |
| V1-022 (number pending) | V1-025 (number pending) | `terraform/` |
| V1-022 (number pending) | V1-026 (number pending) | `terraform/` |
| V1-022 (number pending) | V1-027 (number pending) | `terraform/` |
| V1-022 (number pending) | V1-077 (number pending) | `terraform/` |
| V1-023 (number pending) | V1-024 (number pending) | `terraform/` |
| V1-023 (number pending) | V1-025 (number pending) | `terraform/` |
| V1-023 (number pending) | V1-026 (number pending) | `terraform/` |
| V1-023 (number pending) | V1-027 (number pending) | `terraform/` |
| V1-023 (number pending) | V1-077 (number pending) | `terraform/` |
| V1-024 (number pending) | V1-025 (number pending) | `terraform/` |
| V1-024 (number pending) | V1-026 (number pending) | `terraform/` |
| V1-024 (number pending) | V1-027 (number pending) | `terraform/` |
| V1-024 (number pending) | V1-077 (number pending) | `terraform/` |
| V1-025 (number pending) | V1-026 (number pending) | `terraform/` |
| V1-025 (number pending) | V1-027 (number pending) | `terraform/` |
| V1-025 (number pending) | V1-077 (number pending) | `terraform/` |
| V1-026 (number pending) | V1-027 (number pending) | `terraform/` |
| V1-026 (number pending) | V1-077 (number pending) | `terraform/` |
| V1-027 (number pending) | V1-077 (number pending) | `terraform/` |
| V1-055 (number pending) | V1-056 (number pending) | `frontend/` |
| V1-055 (number pending) | V1-057 (number pending) | `frontend/` |
| V1-055 (number pending) | V1-058 (number pending) | `frontend/` |
| V1-055 (number pending) | V1-059 (number pending) | `frontend/` |
| V1-055 (number pending) | V1-060 (number pending) | `frontend/` |
| V1-055 (number pending) | V1-061 (number pending) | `frontend/` |

## Delivery Checklist
- [ ] V1-006 (number pending) Verify development ownership and preservation inputs
- [ ] V1-055 (number pending) Build the responsive static investor workspace shell
- [ ] V1-073 (number pending) Record legal privacy and advisory release review
- [ ] V1-075 (number pending) Establish isolated Python package and fixture test foundations
- [ ] V1-001 (number pending) Define exact-money scalars and command envelopes
- [ ] V1-007 (number pending) Preserve existing Terraform resource ownership
- [ ] V1-002 (number pending) Define analytical input and result schemas
- [ ] V1-008 (number pending) Review the complete preservation-only Terraform plan
- [ ] V1-044 (number pending) Implement exact paper cost and P&L arithmetic
- [ ] V1-003 (number pending) Define transactional paper and REST schemas
- [ ] V1-009 (number pending) Preserve retry-stable raw ingestion evidence
- [ ] V1-024 (number pending) Define additive analytical source and revision structures
- [ ] V1-025 (number pending) Configure static hosting and invited identity foundation
- [ ] V1-026 (number pending) Configure scale-to-zero API and bounded jobs
- [ ] V1-029 (number pending) Build point-in-time analytical session inputs
- [ ] V1-004 (number pending) Generate the versioned OpenAPI and TypeScript client
- [ ] V1-010 (number pending) Make shared BigQuery loads idempotent and isolated
- [ ] V1-027 (number pending) Configure transactional storage and protected recovery storage
- [ ] V1-030 (number pending) Implement seeded EMA20 and EMA50 with replay anchors
- [ ] V1-031 (number pending) Implement Wilder RSI14 and interruption handling
- [ ] V1-032 (number pending) Implement Wilder ATR14 with labeled no-trade modeling
- [ ] V1-033 (number pending) Calculate complete-window liquidity eligibility
- [ ] V1-035 (number pending) Calculate Growth activity and profitability dimensions
- [ ] V1-036 (number pending) Calculate sector resilience and valuation dimensions
- [ ] V1-038 (number pending) Publish supported dividend facts without composite scores
- [ ] V1-040 (number pending) Implement versioned Firestore repositories and transaction seams
- [ ] V1-050 (number pending) Implement ordered independent recovery-register operations
- [ ] V1-005 (number pending) Extend CI with isolated contract and application checks
- [ ] V1-011 (number pending) Normalize issuer identity and financial category evidence
- [ ] V1-012 (number pending) Implement versioned exchange calendar ingestion
- [ ] V1-014 (number pending) Align existing financial PDF extraction entry points
- [ ] V1-034 (number pending) Implement the versioned trend-confirmation strategy
- [ ] V1-037 (number pending) Compose Growth ratings and independent advisory guards
- [ ] V1-041 (number pending) Enforce verified identity and current invitation admission
- [ ] V1-042 (number pending) Implement recovery-fenced idempotency receipts
- [ ] V1-056 (number pending) Build sign-in verification and password-reset flows
- [ ] V1-057 (number pending) Build the Swing screener and indicator detail
- [ ] V1-058 (number pending) Build Growth rankings and first-class dividend research
- [ ] V1-059 (number pending) Build paper portfolio reporting and order history
- [ ] V1-013 (number pending) Normalize genuine share observations and source sessions
- [ ] V1-015 (number pending) Normalize annual reporting and non-financial inputs
- [ ] V1-018 (number pending) Normalize matching ordinary capitalization evidence
- [ ] V1-019 (number pending) Normalize supported price and share adjustment evidence
- [ ] V1-020 (number pending) Normalize existing dividend payments and coverage
- [ ] V1-021 (number pending) Normalize rating-specific history and loading
- [ ] V1-039 (number pending) Persist immutable analytical batches and readiness manifests
- [ ] V1-043 (number pending) Implement paper setup and versioned preferences
- [ ] V1-045 (number pending) Implement versioned position exit advice
- [ ] V1-052 (number pending) Implement recovery-safe trusted admission changes
- [ ] V1-060 (number pending) Implement confirmed paper commands and uncertain-response handling
- [ ] V1-016 (number pending) Normalize evidenced banking activity and capital inputs
- [ ] V1-017 (number pending) Normalize evidenced insurance activity and solvency inputs
- [ ] V1-046 (number pending) Publish transactionally guarded execution-price revisions
- [ ] V1-047 (number pending) Publish complete immutable analytical serving copies
- [ ] V1-022 (number pending) Package reused ingestion functions with explicit settings
- [ ] V1-048 (number pending) Accept fresh manual orders with atomic reservations
- [ ] V1-023 (number pending) Define explicit ingestion workflow dependencies
- [ ] V1-049 (number pending) Execute or expire pending orders exactly once
- [ ] V1-028 (number pending) Restore approval-gated development delivery automation
- [ ] V1-051 (number pending) Implement restrictive-intent-first portfolio reset
- [ ] V1-076 (number pending) Persist session-ordered position exit references
- [ ] V1-053 (number pending) Implement bounded authenticated analysis and paper reads
- [ ] V1-062 (number pending) Integrate source readiness and daily publication
- [ ] V1-063 (number pending) Implement evidence-aware retention and reset cleanup
- [ ] V1-064 (number pending) Implement isolated restore reconciliation and recovery fencing
- [ ] V1-054 (number pending) Wire protected REST handlers and internal worker entry points
- [ ] V1-069 (number pending) Review actual source and company-sector coverage
- [ ] V1-061 (number pending) Connect all static workspaces to the protected API
- [ ] V1-065 (number pending) Add bounded operational telemetry and backup alerts
- [ ] V1-066 (number pending) Verify cross-store and financial mutation races
- [ ] V1-068 (number pending) Measure pilot latency and calculation placement costs
- [ ] V1-067 (number pending) Verify complete workflows against WCAG 2.2 AA
- [ ] V1-070 (number pending) Evaluate provisional financial rules on point-in-time holdouts
- [ ] V1-071 (number pending) Validate the isolated backup and restore runbook
- [ ] V1-077 (number pending) Configure bounded operational alerts and log retention
- [ ] V1-072 (number pending) Review measured whole-stack pilot operating cost
- [ ] V1-074 (number pending) Assemble pilot acceptance and separate activation approvals

## Reservations And First-Wave Assignments
None. Dispatch is disabled. First-wave work is technically independent local foundations plus restricted infrastructure/compliance review; no agent availability or authorization is presumed. Infrastructure read/plan permission and legal/operator decisions must be established by the future owner.

## Release Gates
Verify source/company-sector coverage, point-in-time financial evaluation, contract/concurrency tests, complete-workflow accessibility, pilot load/batch targets, measured whole-stack cost, isolated restore drill, legal/privacy/disclaimer review and named operator/support. Final launch requires product-owner acceptance. New development schedules remain paused until activation is explicitly approved. Missing data stays unavailable; never relax scoring or recovery safeguards to make a gate pass.
