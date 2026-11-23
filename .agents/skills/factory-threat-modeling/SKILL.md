---
name: factory-threat-modeling
description: Model assets, trust boundaries and threat scenarios for an approved system or proposed architecture.
---

# Threat Modeling

Establish scope, actors, assets, sensitive data, entry points, identities and external dependencies from the supplied architecture or code. Draw or reference data flows and trust boundaries. Record unknowns rather than inventing deployed controls.

For each plausible scenario describe the attacker capability, preconditions, entry point, boundary crossed, affected asset and impact. Consider authorization, authentication, data exposure, untrusted input, dependency and delivery integrity, availability and recovery where relevant. Prioritize using the project's impact and likelihood criteria, or state the qualitative assumptions used.

Map mitigations to specific scenarios, identify current evidence and planned controls, and describe how each control can be verified. Record residual risk and decisions for the accountable owner. When UML is required, save PlantUML .puml sources. This skill produces an architecture assessment. Exploit execution and production changes require their own authorized task.
