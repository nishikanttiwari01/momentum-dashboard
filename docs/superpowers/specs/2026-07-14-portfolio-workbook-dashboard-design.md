# Portfolio Workbook Dashboard Mockup Design

## Objective

Create a standalone HTML mockup that demonstrates how the current-portfolio data in `investment.xlsx` can be represented in the app. The mockup is a review artifact only; it will not alter the application or import workbook data into the running app.

## Workbook Scope

Use current portfolio data from these sheets:

- `BALANCE SHEET`
- `CURRENT ASSET`
- `FUNDS`
- `Funds XIRR`
- `Final XIRR`
- `EQUITY`
- `FIXED ASSET`

Exclude planning, obsolete, sensitive, and unrelated sheets, including:

- `GOALS`
- `MNTHLY INCOM PLAN`
- `PRF REVIEW`
- `MF discont.`
- `Property Cal.`
- `REMIT`
- `STOCKS RECMDN`
- `REF`
- `Gera office roi`
- Empty or temporary sheets such as `SHRI GANESH`, `DASHBOARD`, and `Sheet1`

Never expose workbook login credentials, passwords, account numbers, folio numbers, URLs, or other personal identifiers.

## Mockup Layout

The standalone page uses a hybrid dashboard-and-detail layout consistent with the current portfolio page.

1. A portfolio overview displays total principal, current market value, gain or loss, and overall return.
2. An asset-allocation pie chart shows mutual funds, equity, fixed assets, and any supported cash/debt grouping available in the selected sheets.
3. A mutual-fund allocation pie chart shows categories such as small cap, mid cap, large cap, and debt fund. Its legend shows category, percentage, and invested amount.
4. A historical portfolio chart uses dated principal and market-value snapshots from the workbook.
5. Detail sections show mutual funds, equities, and fixed assets in readable tables with totals and relevant return values.
6. An upload-preview panel demonstrates the future workbook refresh flow.

The mockup will be responsive and self-contained, with no build step or external network dependencies.

## Workbook Refresh Design

The future application should accept `.xlsx` directly. Converting a workbook manually into one large CSV is not recommended because the workbook contains multiple related tables, formulas, snapshots, and transaction histories.

On upload, the backend will:

1. Validate the file type, size, and required sheet names.
2. Read only the approved sheets and approved fields.
3. Normalize Excel dates, currency values, categories, fund names, and cached formula results.
4. Convert the selected data into internal normalized records equivalent to separate CSV tables, such as `portfolio_snapshots`, `instruments`, `holdings`, and `transactions`.
5. Reject invalid rows and report warnings without exposing sensitive cell contents.
6. Show a preview of additions, updates, removals, totals, and validation warnings.
7. Apply changes only after confirmation.

An uploaded workbook replaces the latest portfolio snapshot and holding values. Transaction history already stored in the app is preserved; workbook transactions are deduplicated using instrument, date, amount, NAV/price, and account-owner-neutral identifiers.

## Mockup Interactions

- Allocation legends identify their matching pie slices.
- Detail tabs or section links switch between mutual funds, equity, fixed assets, and upload preview.
- The upload control accepts an `.xlsx` selection locally and displays a simulated validation preview; the mockup does not send or persist the file.
- Tables remain usable on smaller screens through horizontal scrolling.

## Error and Privacy States

The upload preview shows clear states for missing required sheets, malformed dates or numbers, duplicated transactions, and totals that do not reconcile. Sensitive columns are ignored even if present. The UI never displays cell-level passwords, login names, account numbers, folio numbers, or source URLs.

## Validation Criteria

- The standalone HTML opens without a server or build command.
- The allocation pie charts and legends render correctly.
- Values shown in the overview reconcile with the displayed category totals.
- The main current-portfolio sections are represented without planning sheets.
- The upload preview clearly communicates validation and replacement behavior.
- The page contains no workbook credentials or personal account identifiers.
