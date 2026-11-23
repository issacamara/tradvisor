---
name: factory-twelve-factor-app
description: Assess or implement applicable twelve-factor practices for the selected stack and deployment target.
---

# 12-Factor App

Read the selected stack, deployment target and approved constraints. Assess codebase, dependencies, configuration, backing services, build/release/run, processes, port binding, concurrency, disposability, environment parity, logs and administrative processes against the actual application.

For each relevant factor, identify current evidence, gaps and a proportionate action. Preserve declared dependencies and reproducible builds, keep secrets in approved runtime configuration, distinguish persistent state from process state, and check startup/shutdown and background work where applicable. A local deployment may still need these properties. Record factors outside the workload's scope with reasons.

If implementation is requested, work within approved architecture and include validation of the changed behavior. Avoid imposing containers, a cloud service, an identical image policy or horizontal scaling on workloads that do not require them. Link exceptions and residual limits to an owner decision.
