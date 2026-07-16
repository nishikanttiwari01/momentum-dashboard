# Momentum Market Index Charts Design

## Goal

Add a compact Markets section above the existing Century Ply instrument chart on the Momentum page. It gives immediate context from India and the US without changing the existing stock-detail workflow.

## Markets

- Sensex using Yahoo Finance symbol `^BSESN`.
- S&P 500 using Yahoo Finance symbol `^GSPC`.

## User interface

The Markets section contains two equal-width cards on desktop and one card per row on narrow screens. Each card uses the existing Century Ply visual language: a clean blue price line, restrained grid, actual index values, and no gradient area fill.

Each card displays:

- Index name and symbol.
- Latest available value.
- Change and percentage change for the selected period.
- `1M`, `6M`, `1Y`, and `5Y` range controls.
- Loading skeleton, unavailable state, and retry behavior.

The section appears immediately above the existing Century Ply/detail chart. It does not replace or alter the stock chart.

## Data flow

The frontend requests index history from a dedicated backend endpoint. The backend owns the Yahoo symbols, validates the requested range, normalizes dates and closing values, and returns a small chart-ready response. This avoids direct browser calls to Yahoo and keeps error handling consistent with the rest of the application.

The endpoint permits only the configured Sensex and S&P 500 keys. Responses may be cached briefly because index history does not need per-render refetching.

## Failure handling

Failure of one index must not hide the other index or the existing Momentum content. A failed card shows a concise unavailable message and retry action. Empty or invalid upstream data is returned as an unavailable response rather than a fabricated series.

## Verification

- Backend tests cover symbol mapping, range validation, normalized history, and upstream failure.
- Frontend tests cover both cards, range selection, responsive section placement, and independent failure states.
- Production frontend build must complete.
- The rendered Momentum page must show Markets above the Century Ply chart.
