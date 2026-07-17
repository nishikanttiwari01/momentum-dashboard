# Unified Top Movers Design

## Goal

Remove the duplicate Top Performers section from the Momentum page and make Top Movers the single place for ranking stocks by return over short, long, and user-defined periods.

## User experience

Top Movers keeps its current gainers-and-losers presentation and adds period controls for 1D, 1W, 1M, 3M, 6M, 1Y, 5Y, and Custom. Selecting Custom reveals start and end date fields plus an Apply action. A custom request is valid only when both dates are present and the start date is not after the end date. Validation errors appear beside the controls without replacing the current results.

For every period, the displayed percentage is the adjusted-close return between the period boundaries. For custom ranges, each boundary resolves to the nearest available trading-day close inside the selected date range. A stock without valid prices at both boundaries is omitted. The response identifies the actual resolved dates so the UI can make the calculation window clear.

The separate Top Performers card is removed. ETF Watch expands into the space it occupied.

## API and data flow

Extend `GET /api/v1/screener/top-movers` to accept the existing preset `period` values plus `6m`, `1y`, `5y`, and `custom`. Custom requests also require ISO `start_date` and `end_date` query parameters. Supplying custom dates for a preset, omitting either custom date, reversing the range, or selecting a range with no usable trading days returns a structured 400 response.

The endpoint obtains the current screened universe once, reads locally stored adjusted-price history in batches, calculates each eligible stock's return, and ranks the results into gainers and losers. It must not make one external network request per stock. Existing short-period snapshot fields may be used only when they produce the same adjusted-close boundary semantics; otherwise all periods use the historical-price calculation path.

The Top Movers response retains its existing fields and adds requested and resolved date metadata. Its `period` enum is expanded in the OpenAPI contract, and generated frontend types and client code are regenerated through the project's existing contract workflow.

The obsolete `GET /api/v1/screener/top-performers` route and `TopPerformersCard` component are removed after all consumers are migrated.

## Failure and loading behavior

Changing a preset or applying a valid custom range preserves the previous table while the new request loads. Empty results show a clear no-data message. Backend price-data failures produce the existing Top Movers error state rather than partial or fabricated returns. Individual stocks with insufficient history are skipped without failing the whole response.

## Testing

Backend tests cover every preset, true trailing 1Y behavior, 5Y history, custom validation, nearest in-range trading days, adjusted-close returns, missing stock history, deterministic ranking, and the removal of the performers route. Contract tests verify the expanded parameters and response metadata.

Frontend tests cover all period controls, opening and applying Custom, invalid date feedback, request parameters, loading and empty states, resolved-date display, continued gainers/losers rendering, absence of Top Performers, and ETF Watch layout expansion.

## Scope

This change does not alter universe membership, Top Movers eligibility filters, result counts, drawer behavior, or ETF Watch contents. It introduces no new external market-data provider.
