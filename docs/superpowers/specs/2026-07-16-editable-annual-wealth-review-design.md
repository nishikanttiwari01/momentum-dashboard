# Editable Annual Wealth Review Design

## Goal

Turn Annual Review into a persistent January–December analysis workspace. Reuse portfolio data already stored in snapshots, assets, valuations, transactions, family-plan assumptions, and goals. Store only manual corrections and missing historical inputs.

## Data Ownership

Existing portfolio tables remain the source of truth. Annual Review must not copy assets, transactions, valuations, goals, or family-plan assumptions into a second annual table.

A new `portfolio_annual_review_overrides` table stores one optional override record per calendar year. Its nullable fields are:

- opening_net_worth_inr
- contributions_inr
- investment_gain_inr
- property_gain_inr
- rent_received_inr
- withdrawals_inr
- closing_net_worth_inr
- investment_xirr_pct
- notes
- created_at and updated_at

`year` is unique. A null field means “use the calculated/imported value.” Deleting an override field restores the derived value; deleting the record restores all derived values for that year.

## Derived Values

For each year, the service builds a review from existing data before applying overrides:

- Opening net worth: total INR market value from the latest portfolio snapshot dated on or before 31 December of the previous year.
- Closing net worth: total INR market value from the latest snapshot dated on or before 31 December of the selected year, provided that snapshot falls within that calendar year.
- Contributions: positive buy/contribution cash flows from portfolio transactions occurring within the selected year. Transactions are deduplicated by their existing snapshot/source identity.
- Withdrawals: sell/withdrawal transaction cash flows plus actual goal outflows when such persisted events exist. Projected future goal amounts are never treated as historical withdrawals.
- Property gain: closing property value minus opening property value, less net property additions and plus property disposals where those transactions are available.
- Rent received: actual persisted rental receipts when available. The family-plan monthly-rent assumption may be shown as an estimate, but is not silently recorded as actual rent.
- Investment gain: closing financial-asset value minus opening financial-asset value minus net financial contributions.
- Investment XIRR: calculated only when sufficient dated financial cash flows and an ending financial value exist. Otherwise it remains missing until manually entered.

If a source is incomplete, the derived field is null rather than zero. Zero is shown only when the data proves no activity occurred.

## Precedence and Traceability

Displayed value precedence is:

1. Manual override
2. Calculated value from existing portfolio data
3. Missing

Every field returns a source status: `manual`, `calculated`, `imported`, `estimated`, or `missing`. The response also includes a short source explanation and the relevant snapshot dates. This lets the UI explain why a number appears.

## Reconciliation

The service calculates:

`expected closing = opening + contributions + investment gain + property gain + rent received - withdrawals`

It returns the difference between the expected and entered/derived closing value.

- Difference within ₹1,000: Reconciled.
- Larger difference: Needs review, with the exact difference shown.
- Missing required inputs: Incomplete; no false zero or return is shown.

The service never changes a user-entered closing value to force reconciliation.

## API

- `GET /api/v1/wealth-portfolio/annual-reviews` returns all available years assembled from snapshots, transactions, and overrides.
- `GET /api/v1/wealth-portfolio/annual-reviews/{year}` returns one assembled review with field sources and reconciliation.
- `PUT /api/v1/wealth-portfolio/annual-reviews/{year}` upserts nullable override fields and notes, then returns the recalculated review.
- `DELETE /api/v1/wealth-portfolio/annual-reviews/{year}` removes that year’s overrides and returns the recalculated review.

Valid years are 2000 through the current calendar year. Money values may be positive or negative where gains/losses require it, but contributions, rent, opening/closing values, and withdrawals cannot be negative. XIRR is limited to -100% through 1,000%.

## UI

The Annual Review tab loads assembled data from the API and removes the hardcoded sample records.

- Year selector and `Add year` action.
- Compact summary cards for opening value, contributions, investment gain/loss, property gain/loss, rent, withdrawals, closing value, and XIRR.
- Each card shows a source badge and edit action.
- An edit drawer contains all fields for the selected year. Calculated values are prefilled but are not saved as overrides unless changed.
- Changed fields show `Manual override`; each has `Restore calculated value` where a derived value exists.
- Save validates inputs and shows the recalculated reconciliation result.
- Delete overrides requires confirmation and never deletes portfolio source data.
- Wealth bridge and year-by-year table use the assembled effective values.
- Loading, empty, incomplete, save-failure, and validation states provide specific next actions.

## Component Boundaries

- Backend model and Alembic migration: override persistence only.
- Pydantic schemas: annual field value/source, review response, override update.
- Annual review service: derivation, override precedence, XIRR eligibility, and reconciliation.
- Wealth portfolio router: four annual-review endpoints.
- Frontend API/types/hooks: transport and caching.
- `PortfolioAnnualReview`: display and orchestration.
- `AnnualReviewEditor`: focused manual-entry drawer.

## Testing

- Service tests cover missing data, snapshot selection, transaction aggregation, override precedence, restoration, incomplete XIRR, and reconciliation.
- API tests cover list/get/upsert/delete and validation without mutating source portfolio rows.
- Frontend tests cover derived labels, editing, saving, restoring, incomplete years, and request failures.
- Production frontend build and focused backend tests must pass.

## Out of Scope

- Editing the underlying imported portfolio, transactions, property valuations, or goals from Annual Review.
- Treating projected rent or future goals as historical actuals.
- CSV/Excel export and multi-user ownership in this delivery.
