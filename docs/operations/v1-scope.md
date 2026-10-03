# V1 Scope And Operational Boundary

## Product Scope

Tradvisor V1 provides two read-only BRVM research workflows:

- Swing research: daily technical entry state, signal strength, supporting evidence, and close-price charts.
- Long-Term research: Growth ranking, company evidence, and available dividend facts.

The application publishes analytical research only. It does not accept orders, manage cash or positions, maintain simulated or real portfolios, calculate trading P&L, or connect to a broker.

## Serving Boundary

BigQuery remains the source of truth for market and financial inputs. Daily processing creates an immutable analytical publication batch. The API serves the active batch from compact Firestore documents; interactive browser requests do not calculate indicators or query BigQuery directly.

The public V1 API is read-only:

- `GET /v1/me`
- `GET /v1/swing/recommendations`
- `GET /v1/long-term/rankings`
- `GET /v1/stocks/{symbol}`
- `GET /v1/stocks/{symbol}/chart`

## Delivery Boundary

Deploy the committed `V1` branch through the repository development-delivery workflow. It builds the static frontend, builds an immutable API image, applies the reviewed development Terraform configuration, and deploys Firebase Hosting. A successful deployment must be followed by authenticated smoke testing of Swing and Long-Term.

## Data Lifecycle

Retired simulated-trading records are not part of the V1 serving model. Firestore retains only published analytical batches, the active-publication pointer, and admission metadata needed by the API. Do not delete `analysis_batches` or `publication_state` during operational cleanup.

Any future trading, portfolio, or broker capability requires a new product decision, a revised BRD and architecture, explicit data-model design, and separate deployment approval.
