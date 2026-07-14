# Wealth Operating System Design

**Date:** 2026-07-14  
**Status:** Approved design  
**Product:** Modern Wealth Ledger / Portfolio hub

## 1. Purpose

Transform the Portfolio page from a collection of current-value widgets into a household wealth review system. It must consolidate Indian and US holdings, cash/debt, and properties; preserve the existing mutual-fund and QQQ functionality; explain yearly outcomes; track goals; analyze property income; and safely refresh data from `investment.xlsx`.

The dashboard is for interpretation and review. It must answer:

1. What is the household's current market value?
2. Where is wealth allocated and how does it differ from targets?
3. How much capital was added and how much profit was generated each calendar year?
4. Which holdings and asset classes helped or hurt performance?
5. Is the household on track for ₹15 Cr by 31 December 2029?
6. What requires attention because of drift, concentration, or stale/missing data?

## 2. Confirmed product decisions

- The household is shown as one combined portfolio, not separated by owner.
- The primary headline is total market value across investments, cash/debt, and properties. Liabilities are not deducted. The UI label will be **Net worth market value** to match the user's terminology.
- Reporting years run January through December.
- The primary goal is a nominal ₹15 Cr by 31 December 2029; it is not inflation-adjusted.
- Investment XIRR includes Indian mutual funds, stocks, ETFs, debt, and US holdings. Property is excluded from investment XIRR and analyzed separately.
- USD/INR is fetched automatically: live FX for current totals and date-appropriate historical FX for performance calculations.
- Excel remains the upload format. Every successful import creates a permanent dated snapshot instead of overwriting history.
- Property records import from Excel and support dated, auditable in-app valuation overrides.
- Allocation analysis compares current versus editable target allocations and reports percentage and rupee drift. It does not automatically generate buy/sell instructions.
- Goal projections use conservative, expected, and optimistic deterministic scenarios. Monte Carlo analysis is deferred.
- Layout direction **B — Balanced decision dashboard** is approved.

## 3. Information architecture

The existing Portfolio route becomes one Portfolio hub with internal tabs:

### Overview

Consolidated market value, invested capital, investment XIRR, market exposure, asset allocation, wealth history, primary-goal progress, recent changes, and attention items.

### Annual Review

Calendar-year capital flows, investment profit, property appreciation, rent, investment XIRR, blended benchmark, contribution analysis, and rule-based explanations of what worked or did not.

### Investments

All current mutual-fund and QQQ capabilities remain here: buy-only transaction entry, transaction tables, NAV/price charts, transaction dots, weighted average NAV, time-range controls, and sorting. Indian stocks, debt, allocation targets, benchmark returns, and drift analysis extend this tab.

### Properties & Rent

Property valuations, invested cost, appreciation, dated overrides, rent, expenses, occupancy, gross/net yield, yield on cost, and total property return.

### Goals

Pinned ₹15 Cr goal, secondary workbook goals, progress trajectories, required monthly contribution, projected completion dates, and editable three-scenario assumptions.

### Data Import

Upload `investment.xlsx`, validate it, preview changes and warnings, and create an immutable snapshot only after approval.

## 4. Persistent header

The compact Portfolio header remains visible across tabs and displays:

- net worth market value in INR;
- invested capital;
- investment XIRR;
- selected-period change;
- applied USD/INR rate and timestamp;
- last successful portfolio refresh;
- data-health status.

## 5. Overview design

The balanced layout places the following above the first major scroll boundary:

1. consolidated market-value hero;
2. invested capital, XIRR, yearly gain, and goal-progress KPIs;
3. wealth-growth chart alongside allocation;
4. ₹15 Cr progress bar and required monthly contribution;
5. one prioritized actionable insight.

The wealth chart compares market value with invested capital and supports 1Y, 3Y, 5Y, and all-history periods. Values are labeled in Indian units, using ₹ Cr where appropriate.

Allocation shows current versus target values for Indian mutual funds, Indian stocks, US investments, debt/cash, and property. Each category shows current percentage/value, target percentage/value, and overweight/underweight in both percentage points and rupees.

Market exposure shows India, US, and future markets in original currency where relevant and consolidated INR.

## 6. Annual Review calculations

For each calendar year, show:

- opening market value;
- additions and withdrawals;
- investment gain;
- closing market value;
- investment XIRR;
- blended benchmark return and excess return;
- property appreciation;
- rent received and property expenses;
- total market-value change.

The wealth bridge reconciles:

`opening value + contributions - withdrawals + investment return + property appreciation = closing value`

Contribution analysis reports both rupee contribution and percentage return so a large holding is not mistaken for a strong performer. The review identifies top positive/negative contributors, allocation drift, concentration, and data-quality problems.

## 7. Benchmarks

- Indian mutual funds: configurable category benchmark.
- Indian stocks: Nifty 50 TRI.
- US holdings: S&P 500 measured in INR, therefore including currency impact.
- Debt: configurable hurdle rate.
- Combined investments: allocation-weighted blended benchmark.

Benchmark mappings and hurdle rates are editable configuration, versioned with snapshots where they affect historical review.

## 8. Investments behavior

Existing features must remain operational during migration. Mutual-fund NAV charts retain the approved clean, unfilled line style, transaction dots, average-NAV line, labels, and 1M/6M/1Y/5Y/since-inception controls.

Sortable headers always show a faint neutral arrow indicator. The active sort direction becomes prominent and colored. Sorting is stable and places missing values last.

Each holding should expose invested amount, market value, gain, XIRR, benchmark return, excess return, portfolio allocation, target allocation, and drift. Detailed calculations must link to their source transactions and valuation date.

## 9. Properties and rental analytics

Each property shows:

- current market value and valuation date;
- acquisition and improvement cost;
- unrealized appreciation;
- monthly and annual rent;
- occupied/vacant periods;
- maintenance, tax, and other expenses;
- gross rental yield on current market value;
- net rental yield on current market value;
- secondary yield on original cost;
- combined return from rent and appreciation.

The timeline contains purchases, major payments, valuations, overrides, rent receipts, and expenses. Property valuations become stale after a configurable age and trigger a warning.

## 10. Goals and simulator

The primary goal displays current value, achieved percentage, amount remaining, actual versus required trajectory, expected value at the deadline, required monthly contribution, and projected completion date.

Conservative, expected, and optimistic scenarios accept editable monthly contributions, investment return by asset class, property appreciation, and USD/INR assumptions. Scenario values never mutate actual records.

Other workbook goals appear as smaller cards with independent targets, dates, assumptions, and funding sources. Timeline events may represent education spending, property income, or retirement withdrawals.

## 11. Data model

The workbook is converted into normalized records rather than rendered by cell coordinates. Core entities are:

- PortfolioSnapshot
- Asset and Holding
- Transaction/CashFlow
- Valuation
- Property
- RentReceipt and PropertyExpense
- Goal and GoalScenario
- Market, Currency, and FxRate
- Benchmark and BenchmarkObservation
- ImportJob, ImportIssue, and SourceReference
- DatedOverride

Every imported record retains workbook, sheet, and source-row metadata where safe. Stable deterministic identifiers prevent duplicate transactions across repeated uploads.

## 12. Workbook import

The import flow is Validate → Preview → Import.

### Validate

Recognize supported sheets/columns and detect invalid dates, invalid numbers, missing required values, duplicate transactions, inconsistent totals, unsupported structures, and stale inputs.

### Preview

Show additions, updates, unchanged records, ignored sheets, warnings, and blocking errors. The user can cancel without changing portfolio state.

### Import

Write records and an immutable dated snapshot atomically. Any failure rolls back the complete import.

Relevant sources include balance sheet, current assets, funds/XIRR, final XIRR, equity, fixed assets, goals, monthly-income planning, Gera office ROI, and relevant current-portfolio data. `MF discont.`, `Property Cal.`, `REMIT`, and stock recommendations are explicitly excluded and must never be parsed or stored.

## 13. FX rules

- Current USD holdings use the latest successful USD/INR rate.
- Historical cash flows and valuations use the rate effective on their date.
- Original amount/currency and converted INR amount/rate are both retained.
- UI surfaces rate source timestamp and cached-fallback status.
- Missing historical rates are warnings and use a documented fallback policy; silent substitution is prohibited.
- The model supports future currencies and markets without schema changes to holdings.

## 14. Overrides and auditability

In-app property overrides are effective-dated and append-only. They do not edit the imported record. The UI shows original value, active override, effective date, note, and history. The same pattern can later support corrections to other imported values.

## 15. Rule-based intelligence

Insights are calculated, traceable observations rather than automated financial advice. Initial rules cover:

- largest positive and negative contributors;
- allocation drift and concentration;
- progress ahead of/behind goal trajectory;
- unusually large return or valuation movements;
- stale NAV, FX, and property valuations;
- duplicate or missing transactions;
- reconciliation failures;
- required monthly contribution changes.

Each insight links to its input values and calculation.

## 16. Error handling and trust

- Imports are atomic and preserve the prior valid snapshot.
- Blocking errors and non-blocking warnings are visually distinct.
- Partial histories do not produce misleading XIRR; they show an insufficient-data state.
- Reconciliation discrepancies are visible and never silently forced to zero.
- Loading, empty, stale, fallback, and unavailable states are explicitly designed.
- No ignored or sensitive sheet contents enter logs, database records, previews, or client payloads.

## 17. Accessibility and responsive behavior

The hub uses a restrained, attractive palette with accessible contrast. Color never carries meaning alone. Charts provide labels/tooltips and table equivalents for key data. Tabs and sortable headers are keyboard accessible. On narrower screens, panels stack and tables scroll internally; the page does not depend on an ultra-wide canvas.

## 18. Verification strategy

Automated tests cover:

- workbook validation and repeat-import idempotency;
- duplicate detection and atomic rollback;
- XIRR and weighted-average NAV;
- historical/current FX conversion;
- Jan–Dec yearly reconciliation;
- benchmark and blended-benchmark calculations;
- rental-yield formulas;
- goal projection scenarios;
- stable/null-last sorting;
- insight-rule thresholds.

Browser tests use representative imported data to verify all tabs, responsive layouts, transaction entry, sort indicators, and rendered chart ranges. Five-year and since-inception mutual-fund charts must be visually rendered and checked for sane dates and Y-axis values before completion is claimed.

## 19. Delivery phases

1. Foundation: importer, normalized records, snapshots, FX, consolidated header, and sort indicators.
2. Overview: balanced layout, wealth chart, allocation/market exposure, goal bar, and snapshot changes.
3. Annual Review: yearly reconciliation, XIRR/benchmarks, attribution, and insights.
4. Properties: valuations, overrides, rent/expense ledger, and yields.
5. Goals: primary/secondary goals and three-scenario simulator.
6. Refinement: responsive polish, accessibility, performance, and optional future Monte Carlo planning.

Each phase must preserve existing Portfolio functionality and ship with its own migration, tests, and browser verification.

## 20. Out of scope for the initial delivery

- liability deduction;
- owner-specific sub-portfolios;
- inflation-adjusted primary goal;
- automated buy/sell recommendations;
- Monte Carlo probability analysis;
- parsing ignored workbook sheets;
- property inclusion in investment XIRR.
