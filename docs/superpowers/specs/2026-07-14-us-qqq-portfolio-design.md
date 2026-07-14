# US QQQ Portfolio Design

## Goal

Add a USD-denominated US Investments section to the Portfolio page, initially containing Invesco QQQ. The user can enter BUY transactions directly in the page, review the position and its weighted average cost, and compare every purchase with QQQ's historical market price before deciding whether to add another lump sum.

This release activates transaction entry only for QQQ. The transaction model and UI boundaries should remain generic enough to support Indian mutual funds later without redesigning the workflow.

## Scope

### Included

- A separate US Investments section below the existing Indian mutual-fund section.
- One configured instrument: QQQ, denominated entirely in USD.
- BUY-only transaction entry from the Portfolio page.
- Local persistent transaction storage in a table-shaped CSV file managed through backend APIs.
- QQQ position totals and historical price chart.
- Purchase markers and a weighted-average-cost reference on the chart.
- A transaction history table beneath the chart.
- Automated tests for calculations, validation, persistence, API output, and the main UI flow.

### Excluded

- SELL transactions and realized-gain calculations.
- Currency conversion or aggregation into the INR portfolio summary.
- Transaction entry for Indian mutual funds in this release.
- Broker integration, order placement, tax-lot accounting, dividends, and foreign-exchange gains.

## Architecture

Implement US investments as a focused module alongside the existing AMFI mutual-fund portfolio pipeline. Reuse presentation conventions and generic transaction concepts, but keep QQQ's USD market prices and totals separate from Indian NAV and INR calculations.

The backend will expose a US-investment overview, a ranged price-history response, and a BUY-transaction creation endpoint. A dedicated local CSV will be the source of truth for user-entered US transactions. Writes must validate the complete request before updating the file and must use an atomic replacement so a failed write cannot corrupt existing transactions.

QQQ configuration should identify the ticker, display name, asset type, and USD currency without hard-coding those attributes throughout calculation and UI code. The implementation may use the project's existing market-data conventions and cache, while keeping the data provider behind a service function that tests can replace.

## Transaction Model

Each BUY transaction contains:

- A stable generated transaction ID.
- Instrument ID or ticker, initially QQQ.
- Purchase date and time.
- Quantity, which must be greater than zero and may be fractional.
- USD price per unit, which must be greater than zero.
- Optional USD fees, defaulting to zero and never negative.

The page form collects purchase date/time, quantity, price per unit, and optional fees. The backend is authoritative for validation and generated fields. On success, the new row is persisted and all QQQ queries are refreshed immediately.

For BUY-only holdings:

- Total units = sum of purchased quantities.
- Total invested = sum of `(quantity × price) + fees`.
- Weighted average buy price = total invested / total units.
- Current value = total units × latest QQQ market price.
- Unrealized gain/loss = current value − total invested, also expressed as a percentage of total invested.

Fees are therefore included in the displayed average cost. Values and labels remain in USD. No QQQ amount contributes to the INR summary.

## API and Data Flow

The Portfolio page loads the existing Indian overview independently from the new US overview. A failure in one section must not hide the other.

The US overview returns configured instruments, their latest available prices, calculated holding summaries, and stored transactions. The ranged history endpoint supports `1m`, `6m`, `1y`, `5y`, and `max`, returning chart-ready daily QQQ price points and purchase events within the visible range. Purchase events retain their actual transaction price even when the market-price series is daily.

Submitting the form posts one BUY transaction. After a successful response, the client invalidates both the US overview and active QQQ history query so the summary, markers, average line, and transaction table update together.

## User Interface

The US Investments section uses the existing Portfolio page's Material UI table and expandable-row treatment. Its QQQ summary row displays:

- Latest price.
- Total units.
- Total invested.
- Average buy price.
- Current value.
- Unrealized gain/loss.
- An Add transaction action.

Expanding QQQ reveals a chart styled consistently with the existing mutual-fund NAV chart. Range controls are 1M, 6M, 1Y, 5Y, and Max.

The chart contains:

- A blue QQQ market-price line.
- A visible dot for every BUY in the selected range, positioned at its actual purchase price.
- A dashed horizontal line at the current weighted average buy price.
- Tooltips for price points and purchases. A purchase tooltip shows date/time, quantity, purchase price, fees, and total invested for that transaction.
- A label stating the latest price's percentage above or below the weighted average cost.

The current weighted average is intentionally used as the stable comparison line. The transaction dots preserve the sequence and prices of earlier purchases. A newest-first transaction table under the chart provides the exact source records.

The Add transaction form opens from the QQQ row. It prevents submission while required values are missing or invalid, reports backend errors without closing the form, and closes only after a confirmed save.

## Error Handling

- Invalid instrument, date/time, quantity, price, or fees returns a clear 4xx validation response and does not change the CSV.
- Duplicate generated IDs are prevented by the backend.
- Market-data failures preserve and display stored transactions and calculated invested cost, while price-dependent fields show as unavailable.
- The UI shows a section-level market-data warning without replacing the entire Portfolio page.
- Empty transaction state displays zero units and invested cost, no average-cost line, and guidance to add the first purchase.
- Cache or provider failures may fall back to valid stale price data when the existing market-data policy permits it, with freshness made visible in the response/UI.

## Testing

Backend unit tests cover BUY validation, fractional quantities, fee-inclusive weighted average cost, empty holdings, and unavailable market prices. Persistence tests verify CSV round trips and that rejected writes leave the file unchanged. API/service tests use deterministic QQQ price fixtures to verify ranges, latest-price calculations, purchase markers, and above/below-average comparisons.

Frontend tests cover the empty state, opening and validating the form, successful submission/query refresh, USD formatting, summary values, chart range changes, purchase marker data, average-cost labeling, and a price-provider error that still leaves transactions visible.

Build, focused backend tests, and focused frontend tests must pass before completion.

## Future Extension

Indian mutual funds can later adopt the same transaction form, persisted transaction contract, purchase-marker model, and average-cost presentation. Their existing AMFI NAV history and INR formatting remain provider- and currency-specific; the reusable boundary is the validated BUY transaction and derived holding summary, not a forced merger of US-price and AMFI-NAV services.
