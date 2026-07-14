# Indian Mutual-Fund Transaction Tracking Design

## Goal

Give every configured Indian mutual fund the same purchase-tracking experience as QQQ: direct BUY entry on the Portfolio page, a combined holding summary, purchase markers on the NAV chart, a fee-inclusive average purchase NAV, and a visible transaction table. All Indian values remain in INR.

## Scope

This release supports BUY-only entry for every configured instrument whose type is `mutual_fund`. Existing BUY and SIP rows in `data/portfolio_transactions.csv` remain compatible and appear in the combined view. SELL entry, editing, deletion, database migration, broker integration, and account-specific views are excluded.

## Storage and Accounts

The page presents transactions as tables, matching the QQQ experience. Persistence remains the existing CSV ledger behind the Portfolio API.

Accounts are intentionally hidden. When a new purchase is submitted, the backend selects the first `holdings_config` account configured for that fund. Existing rows retain their stored account IDs, but all accounts are aggregated into one fund summary, one average NAV, one chart, and one transaction table.

Writes validate the full transaction before touching the file and replace the ledger atomically. Existing comments and valid rows must remain intact where practical; the persisted ledger remains readable by the current loader.

## Transaction Entry

Each fund row has an Add transaction action. The form collects purchase date, amount invested, NAV, units, and optional fees. The user must supply NAV plus at least one of amount or units:

- Amount and NAV derive units as `amount / NAV`.
- Units and NAV derive amount as `units × NAV`.
- If amount and units are both supplied, they must agree within a small rounding tolerance.
- NAV, amount, and units must be finite and positive; fees must be finite and non-negative.

The stored type is BUY. The purchase date uses the ledger's existing date-only format because mutual-fund NAVs are daily. After a confirmed save, the overview and active fund-history query refresh together.

## Calculations

For the combined fund view:

- Total units are the sum of BUY/SIP units across accounts.
- Total invested is the sum of purchase amounts plus fees.
- Average purchase NAV is total invested divided by total units, so fees are included in cost basis.
- Current value is total units multiplied by the latest NAV.
- Unrealized gain/loss is current value minus total invested, shown as INR and percentage.

Existing portfolio summary, XIRR, allocation, and accumulation calculations continue to use the same ledger. QQQ remains separate in USD.

## API and Chart Data

The existing Portfolio API gains a validated BUY endpoint. The NAV-history response gains purchase events for the requested fund and selected range, plus the combined average purchase NAV and latest-NAV-versus-average percentage.

Each purchase event includes date, amount, units, NAV, fees, and derived invested cost. Events use their actual purchase NAV for vertical placement and are not snapped to the market NAV series.

## User Interface

Each mutual-fund summary row adds total units, average NAV, gain/loss, and an Add transaction button while retaining current performance fields. Clicking the button does not toggle the expanded chart.

The expanded chart keeps its existing range controls and NAV line, and adds:

- A purchase dot for every BUY/SIP in the visible range.
- A dashed horizontal average-purchase-NAV line.
- A label stating whether the latest NAV is above or below the average.
- Purchase tooltips containing date, units, NAV, fees, and invested amount.
- A newest-first combined transaction table beneath the graph.

When no purchases exist, the chart remains available and the UI invites the user to add the first purchase. If AMFI data is unavailable, stored transactions and invested totals remain visible while NAV-dependent values show as unavailable.

## Error Handling and Testing

Invalid fund IDs, dates, inconsistent amount/unit combinations, non-positive values, and negative fees return clear validation errors without changing the ledger. Funds without a configured holding account reject entry with an actionable error.

Backend tests cover derivation in both directions, consistency tolerance, automatic first-account assignment, atomic persistence, fee-inclusive average NAV, combined-account aggregation, ranged purchase events, and offline NAV behavior. Frontend tests cover form validation, successful refresh, INR formatting, chart markers, average line/label, combined transaction ordering, and independent failure states. Focused tests and the production frontend build must pass before completion.
