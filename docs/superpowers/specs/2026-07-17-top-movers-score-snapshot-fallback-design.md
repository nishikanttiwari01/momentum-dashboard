# Top Movers Score-Snapshot Fallback Design

## Problem

Top Movers currently returns `no_trading_data` because the configured `backend/parquet/prices` directory is empty. The installation does have 495 daily score snapshots through 16 July 2026, including symbol, date, and closing-price data.

## Data-source priority

Top Movers first uses the dedicated prices dataset when it contains usable rows for the requested universe and window. When that dataset is absent, empty, or contains no usable rows, it falls back to the local daily score-snapshot archive. It does not call an external market-data provider.

The fallback reads the required score snapshots as a batch, extracts each eligible symbol's stored closing price, and feeds the existing return-ranking logic. The dedicated prices dataset remains the preferred source for adjusted-close calculations; the fallback uses the close stored in each score snapshot.

## Window resolution

For `1D`, the fallback uses the latest two available score-snapshot dates. Other presets and custom ranges use the nearest available snapshot on or after the requested start and on or before the requested end.

When the requested start predates the archive, including for `5Y`, the fallback uses the earliest available snapshot. The response retains the requested dates and reports the actual shorter resolved dates so the Momentum page displays the calculation period honestly.

A symbol needs positive finite prices at two distinct resolved dates. Symbols without sufficient data are omitted. If no eligible symbol has a valid pair in either source, the endpoint keeps the existing structured `no_trading_data` response.

## Integration boundaries

The fallback belongs in the Top Movers history service, behind the same return-row interface used by the endpoint. The endpoint continues to own eligibility, metadata enrichment, deterministic gainers/losers selection, drawer actions, and response construction. Existing API and frontend contracts do not change.

## Testing

Service tests cover source priority, empty-price fallback, latest-two `1D` snapshots, preset and custom boundaries, start dates before archive history, invalid or missing snapshot prices, and failure when both sources are empty. An API regression test reproduces the production condition—current score snapshots plus an empty prices dataset—and verifies a successful response with requested and shortened resolved dates.

Frontend behavior is already contract-compatible; its resolved-range rendering and error handling remain unchanged.
