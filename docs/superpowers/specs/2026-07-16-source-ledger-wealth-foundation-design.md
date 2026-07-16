# Source-Ledger Wealth Foundation Design

## Goal

Replace workbook-total-driven portfolio analysis with a normalized wealth ledger. Import underlying assets, dated principal observations, market valuations, cash flows, income receipts, and FX rates once; calculate Overview, Annual Review, Properties, Goals, and future analytics from those facts. Workbook report sheets become reconciliation checks, not authoritative inputs.

## Workbook Findings

The workbook has three different data classes that must not be mixed:

1. **Source facts**
   - `CURRENT ASSET`: household owners, asset descriptions/categories, dated principal and market-value observations from 10 November 2023 through 25 April 2026.
   - `FIXED ASSET`: individual properties with dated principal and market values, plus dated Brigade payments.
   - `FUNDS`: individual mutual-fund identity, category, principal, and current market value.
   - `Funds XIRR`: dated mutual-fund purchases and terminal valuations.
   - `EQUITY`: individual equity holdings with owner, principal, and market value.
   - `Final XIRR`: consolidated dated investment cash-flow series and terminal values.
   - `Gera office roi`: dated actual property income and expense entries where present.

2. **Assumptions and projections**
   - `MNTHLY INCOM PLAN`: income scenarios and future projections. The manually entered Gera and Golfhome monthly rent values are current assumptions, not historical receipt transactions.
   - `GOALS`, `PRF REVIEW`, and projection sections: planning assumptions and future scenarios.

3. **Calculated reports**
   - `BALANCE SHEET`: formulas pulling annual values from `CURRENT ASSET` and `FIXED ASSET`.
   - Summary blocks in `FUNDS`, `CURRENT ASSET`, `FIXED ASSET`, and `EQUITY`.

`BALANCE SHEET` therefore validates ledger calculations. It must not be imported as a second copy of wealth facts.

## Canonical Data Model

### Import audit

`portfolio_imports` and `portfolio_snapshots` remain immutable import audit records. They identify the workbook version and import time but are not the analytical source of asset values.

### Stable assets

Create `wealth_assets`:

- id
- stable source key
- household owner
- name and description
- asset class and category
- market and currency
- active flag
- created/updated timestamps

An asset exists once across imports. Examples are one mutual-fund folio, one equity holding, one savings account, Brigade land, Amrapali flat, and Gera office.

### Observations

Create `wealth_asset_observations`:

- id and asset_id
- observed_on
- principal_in_native_currency
- market_value_in_native_currency
- currency
- observation granularity: `asset`, `asset_group`, or `household_group`
- source import ID
- source sheet, cell/row/column, and workbook heading
- deterministic source fingerprint

The unique key is asset/source fingerprint/observed date. Re-importing an unchanged workbook is idempotent. A newer workbook may add observations without duplicating previous ones.

`CURRENT ASSET` produces dated observations per owner and row. Columns containing only market value create market-only observations. Paired `PRINCIPAL`/`MKT VALUE` columns create complete observations.

`FIXED ASSET` produces dated observations for each property. Repeated same-date column pairs are accepted only when values differ and retain column lineage; the latest column wins for the same property/date while earlier values remain auditable.

### Reporting-period selections

Create `wealth_reporting_periods` and `wealth_reporting_period_sources` to preserve which underlying observations define each workbook reporting year without copying their values.

- reporting year and label, such as `FY-2024`
- period start/end convention
- source observation or source-cell reference for financial principal, financial market value, property principal, and property market value
- source import and formula lineage

This is necessary because the workbook’s FY labels do not always use a simple 31 December observation. For example, BALANCE SHEET FY-2024 selects specific January/February 2025 source cells. The database stores references to those source observations, not duplicate annual totals. The UI shows both the reporting label and actual selected observation dates.

### Cash flows

Create `wealth_cash_flows`:

- id and optional asset_id
- occurred_on
- flow type: contribution, purchase, sale, withdrawal, fee, property_capital, rent, dividend, interest, or goal_outflow
- amount and currency
- actual/projected flag
- source import and source reference
- deterministic fingerprint

Rules:

- Negative `Funds XIRR` and `Final XIRR` values are investment outflows/contributions.
- Positive terminal values on the workbook’s latest valuation date are valuations, not income.
- Brigade payment rows are `property_capital` cash flows.
- `MNTHLY INCOM PLAN` rent values are assumptions and never converted into historical rent receipts.
- `Gera office roi` entries are imported as actual rent/expense cash flows only when their date, amount, and meaning are unambiguous; ambiguous rows generate import warnings.

### Assumptions

Planning assumptions remain in goal/family-plan tables. Add asset-specific income assumptions only where needed, with effective dates. Actual and projected data are never combined in historical return calculations.

### FX rates

Existing dated FX rates remain canonical. Every analytical response preserves native currency and uses the latest persisted rate on or before the fact date. Missing FX produces a missing calculation with an explanation, not a zero.

### Manual overrides

Annual-review overrides remain a separate final precedence layer. They correct or fill missing calculated fields but never modify ledger facts.

## Import Mapping

### CURRENT ASSET

- Rows 3–27 are source asset groups identified by owner, description, and category.
- Row 1 is the observation date.
- Row 2 defines whether a column is market-only or principal/market.
- Rows 17, 27, and 29 are formula totals and are reconciliation checks only.
- Notes in row 30 become import audit notes, not cash flows unless a separate dated source transaction supports them.
- BALANCE SHEET formula references identify which of these observations are selected for FY-2024, FY-2025, and FY-2026 reporting periods. The formulas provide selection lineage only; their cached totals are reconciliation controls.

### FIXED ASSET

- Rows 2–4 create stable property assets.
- Dated principal/market column pairs create property observations.
- Rows 12–19 create Brigade property-capital cash flows.
- Rows 5–8 and 20–22 are calculated totals/checks.

### FUNDS, Funds XIRR, EQUITY, Final XIRR

- `FUNDS` and `EQUITY` create/resolve stable detailed assets and current observations.
- `Funds XIRR` creates detailed mutual-fund purchases and terminal valuations.
- `Final XIRR` is used as a consolidated XIRR reconciliation series. A flow already represented in detailed fund transactions is linked/deduplicated, not inserted twice.
- Differences between a detailed asset sum and its matching `CURRENT ASSET` group observation are surfaced as reconciliation differences.

## Calculation Engine

All portfolio sections use a shared service that queries the ledger as of a requested date.

### Point-in-time wealth

For each active asset, use the latest observation on or before the requested date, convert at effective FX, and sum by asset class, owner, market, and currency.

### Annual Review

Annual Review uses the workbook reporting-year selections when they exist, while retaining the user’s January–December label convention. If a reporting-year selection is absent, it falls back to true point-in-time 31 December observations. The response explicitly identifies which method was used.

- Opening financial/property value: previous reporting period’s selected closing observations, or point-in-time 31 December fallback.
- Closing financial/property value: selected underlying observations for the reporting year, or point-in-time 31 December fallback, with actual observation dates shown.
- Contributions: actual contribution/purchase/property-capital flows during the year, excluding transfers between owned accounts.
- Withdrawals: actual sale/withdrawal/goal-outflow flows, excluding internal transfers.
- Investment gain: closing financial value minus opening financial value minus financial contributions plus financial withdrawals.
- Property gain: closing property value minus opening property value minus property capital additions plus property disposals.
- Rent: actual rent receipts only.
- Investment XIRR: dated external financial cash flows plus opening and closing financial values.
- Net-worth bridge reconciles opening, external flows, investment/property gains, actual income, and closing value.

For the current workbook, expected source-derived checkpoints are:

- FY-2024 closing net worth: ₹58,254,009.25.
- FY-2025 opening: FY-2024 closing; FY-2025 closing: ₹82,510,481.25.
- FY-2025 financial gain after additions: ₹2,963,721, matching the workbook report formula.
- FY-2026 opening: FY-2025 closing; latest FY-2026 closing: ₹83,058,852.25.
- FY-2026 financial gain after additions: -₹513,229, matching the workbook report formula.

The UI must say `FY-2026 · latest selected observation 25 Apr 2026` rather than implying that an April value is a completed 31 December 2026 close.

## Reconciliation

After ledger import, calculate workbook-equivalent controls:

- Per-date `CURRENT ASSET` row totals.
- Per-date property totals.
- Detailed funds/equity sums versus their current-asset group values.
- Total principal and total market value versus `BALANCE SHEET` cached formula results.
- Calculated detailed XIRR versus `Final XIRR` cached result.

Differences within ₹1 are reconciled. Larger differences are stored as import issues with source references. Reconciliation values are not inserted into the ledger to force agreement.

## Migration and Compatibility

The existing snapshot-scoped `portfolio_assets`, `portfolio_transactions`, and `portfolio_valuations` remain readable during migration but stop being the primary analytical source after ledger backfill succeeds.

Migration sequence:

1. Create ledger tables without deleting existing data.
2. Import and verify the workbook into ledger tables.
3. Switch Wealth Summary, Annual Review, Overview, Properties, and Goals to the shared ledger query service.
4. Keep compatibility reads temporarily for an installation without ledger data.
5. Remove compatibility storage only in a later explicitly approved cleanup.

This avoids destructive migration and prevents partially migrated data from breaking the working portfolio.

## API and UI Impact

- Workbook preview reports counts for assets, observations, actual cash flows, assumptions, and reconciliation issues.
- Commit remains atomic: either the ledger and audit import both succeed or neither changes.
- Wealth Summary and Annual Review return `as_of` and field provenance.
- Data Import includes a reconciliation panel showing calculated ledger totals against workbook report totals.
- Existing manual Annual Review overrides continue to work above ledger calculations.

## Testing and Acceptance

- Parser tests use formulas and cached values matching the real workbook layout.
- Import tests prove idempotency and no double counting across sheets.
- Ledger tests prove point-in-time selection, FX conversion, internal-transfer exclusion, actual/projected separation, and source lineage.
- Reconciliation tests prove FY-2024–FY-2026 totals and gains listed above.
- Re-import the real `investment.xlsx` and query the live Annual Review API.
- Render Annual Review and verify FY-2024, FY-2025, and FY-2026 display the expected values and actual observation dates.

## Out of Scope

- Importing `Property Cal.`, `REMIT`, `MF discont.`, or `STOCKS RECMDN`.
- Treating goal projections, passive-income scenarios, or PRF REVIEW estimates as historical facts.
- Deleting legacy snapshot data in this delivery.
