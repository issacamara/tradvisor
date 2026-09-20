# Tradvisor - Extraction Cost Benchmark (Superseded)

**Status:** Superseded; no benchmark required
**Date:** 2026-09-20

## Correction

The stakeholder confirmed that financial-report PDF processing is already addressed by `archive/legacy-ingestion/scripts/scrape_financials.py` and `scrape_financials_init.py`. Reuse this pipeline, including its existing downstream `insert_financials.py` path, rather than introducing a new extraction implementation.

The previous sample request and standalone benchmark procedure are withdrawn. No additional PDFs or EUR 1/month extraction allowance are required for architecture review. Verify integration, extracted-field contracts and actual operating costs during delivery alongside whole-stack cost checks.

No provider calls, report processing, paid benchmark or production runs were performed or authorized by this correction. This note is retained only as a decision record; the current direction is recorded in [Architecture section 11](tradvisor_architecture.md#11-assumptions).
