# V1 Effectiveness Evaluation

The evaluator uses a predeclared holdout of immutable, known-at evidence. It reports total return, drawdown, turnover, denominator-sensitive coverage, and symbol concentration. Fees, liquidity eligibility, and the manual next-close limitation are included in the input contract.

No action is evaluated when its next-close evidence was unavailable, and the evaluator refuses actionable rows without known-at outcomes. The holdout is not used to tune thresholds or calibrate probabilities. Unit tests demonstrate arithmetic and look-ahead refusal; they do not prove investment effectiveness.

The current release has no approved live holdout extract in this repository. Therefore actionable publication still requires explicit product-owner review of the resulting report.
