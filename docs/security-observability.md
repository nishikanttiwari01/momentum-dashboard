# Non-Functional Requirements, Security, and Observability

- **Logging**: correlation IDs (MDC-like), request latency, `run_id`, row counts, error boundaries.
- **Idempotency**: `Idempotency-Key` headers for POST /scan and other mutating endpoints to avoid duplicate work.
- **Input Validation**: Pydantic at API boundary, plus domain-level checks.
- **Time**: store UTC everywhere; frontend localizes display.
- **Performance**: use columnar scans over Parquet; limit to necessary columns; cache Yahoo calls with short TTL.
- **Testing**: seedable fixtures for prices; MSW for FE; contract tests against OpenAPI.