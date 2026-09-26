# V1 Coverage Matrix

This is the release-facing coverage statement for the current BRVM source set. It records what the product may publish, what remains partial, and what must stay visibly unavailable. It does not contain private extracts or copied sample data.

## Evidence Boundaries

| Area | Current evidence | V1 publication rule |
| --- | --- | --- |
| Company universe and sector | Normalized company reference produced by the existing ingestion pipeline | A company remains in the universe only when its normalized identity and sector are present; missing classification is visible as unavailable |
| Daily shares and traded value | Normalized exchange-session share observations | Swing is available only after the required EMA/RSI/ATR/traded-value warm-up and current-session guards pass |
| Annual financials | Ingestion contracts support normalized annual statements; the supplied source set may omit 2024 | Growth is partial or insufficient-evidence when a required period is absent; no missing-year interpolation |
| Dividends | One verified year is currently available | Dividend research is shown with its coverage window; V1 dividend scoring remains explicitly deferred |
| Ratings | Normalized rating evidence when supplied by the source | Missing ratings remain an evidence gap and do not silently remove a company |

## Company and Workflow Matrix

| Coverage state | Company/category condition | Growth | Current advice | Swing warm-up | Blocking semantics |
| --- | --- | --- | --- | --- | --- |
| Full | Required normalized financial dimensions and periods are present | Publish score and reasons | Publish when the relevant latest evidence is current | Publish after the required session warm-up | Normal guards must pass |
| Partial | Some permitted evidence is present but one or more dimensions/periods are absent | Publish only with `insufficient_evidence` or an explicitly partial explanation | Do not imply a complete view | Publish only if the independent Swing evidence is complete | Missing dimensions remain visible |
| Unavailable | Identity, required evidence, or current-session validity cannot be established | No score | No actionable advice | No recommendation | Return an unavailable state and reason |

The matrix applies per company and per workflow. Sector membership is not a substitute for company evidence, and a missing company does not silently disappear from a sector aggregate.

## Owner Acceptance and Scope

The product owner accepts this usefulness rule for V1: publish only evidence-backed results, show partial or unavailable states explicitly, and keep missing source periods visible. Any request to turn a partial row into an actionable score, interpolate a missing year, or activate dividend scoring is a scope decision for a later review, not a test-data decision.

## Validation Commands

The focused checks for this document assert the required source-gap and blocking language without importing private samples:

```text
python3 -m pytest tests/validation/test_coverage.py
```
