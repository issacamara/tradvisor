---
name: factory-test-strategy-design
description: Design risk-based verification and test cases linked to requirements and acceptance criteria.
---

# Test Strategy and Design

Map observable outcomes to acceptance criteria and identify failure modes with practical consequences. Inspect existing checks, interfaces, supported inputs and deployment constraints before adding tests. Prioritize boundaries, invalid input, existing-data compatibility, partial failure and concurrency when the behavior supports them.

Select unit, integration, end-to-end, manual and deployment checks according to what each can establish. Prefer tests through normal entry points and observable outcomes. Avoid tests that merely restate implementation details or generated wording. For a reproducible defect, design a failing test that passes after the correction.

For generated repositories, exercise the real generator for each supported target, inspect rendered outputs, preserve provenance and verify destination collision behavior. Do not present template validation as an application deployment test.

Return a compact mapping from AC to test, environment or artifact identity, expected result and evidence. Keep missing checks and residual risk explicit. Implementation changes still require the project's tests, lint, build and security scanning.
