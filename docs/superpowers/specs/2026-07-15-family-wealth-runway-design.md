# Family Wealth Runway — Design Specification

Date: 2026-07-15
Status: Approved design, pending implementation plan

## Purpose

Extend the existing single-goal simulator into a family wealth runway that answers whether the household can reach ₹15 Cr by 2029, generate ₹2 lakh per month by 2029, and still fund education, a Bangalore house, and two marriages from one combined portfolio.

This is a planning tool, not investment advice. Every projection must identify its calculation date and assumptions.

## Product decisions

- Keep **₹15 Cr by 2029** as the pinned primary goal.
- Treat all other objectives as linked goals drawing from one combined household balance sheet; do not create artificial funding buckets.
- Use a runway-first page layout.
- Project monthly internally and present January-to-December annual summaries.
- Support conservative, expected, and optimistic scenarios.
- Keep all seeded assumptions editable and persisted independently of workbook imports.
- Design the model so Monte Carlo, tax, currency, and estate-planning analysis can be added later, but exclude them from this version.

## Recommended defaults

### Household assumptions

| Assumption | Default |
|---|---:|
| Monthly investment | ₹6,00,000 |
| Annual investment step-up | Optional checkbox, 6% when enabled |
| Real-estate appreciation | 6% annually |
| Current rent | ₹45,000 per month |
| Annual rent increase | 6% |
| Reinvest rent | Enabled until the passive-income start date |
| Sustainable withdrawal rate | 3.5%, editable |

The annual investment step-up is disabled by default so the initial baseline matches a constant ₹6 lakh monthly investment. Enabling it raises the monthly contribution by 6% each January.

### Linked goals

| Goal | Current-value amount | Due | Inflation | Treatment |
|---|---:|---|---:|---|
| Child 1 education | ₹2 Cr | Six years from plan base date | 8% | Permanent expense |
| Bangalore house | ₹3 Cr | User age 52 | 8% | Asset conversion |
| Child 2 education | ₹2 Cr | Twelve years from plan base date | 8% | Permanent expense |
| Child 1 marriage | ₹50 L | User age 58 | 6% | Permanent expense |
| Child 2 marriage | ₹50 L | User age 60 | 6% | Permanent expense |
| Passive income | ₹2 L/month | 2029 | 6% for later comparisons | Recurring income target |

All names, amounts, dates, inflation rates, priorities, and enabled states are editable. Age-derived defaults are converted into explicit dates when the plan is seeded, avoiding calculations that silently shift with the current date.

The ₹2 lakh monthly passive-income target includes rental income. The investment portfolio only needs to sustainably cover the remaining gap.

## Planning model

The imported portfolio snapshot supplies current financial assets, property, land, market exposure, and valuation date. The family-plan configuration supplies future contributions, rent, returns, inflation, and goal events.

The model distinguishes:

- **Financial assets:** mutual funds, stocks, ETFs, debt, cash, and US holdings converted to INR by the portfolio layer.
- **Existing real estate:** rental property and land.
- **Future house:** created when the Bangalore-house goal is funded.
- **Permanent expenses:** education and marriage outflows.
- **Asset conversions:** construction cost leaves financial assets and enters property value in the same period.

Workbook imports update current portfolio values but never overwrite family-plan assumptions. Updating planning assumptions never mutates imported snapshots.

## Projection calculation

For each scenario, calculate monthly from the latest snapshot date through the final enabled linked goal, subject to the existing safe maximum projection horizon.

For each month:

1. Apply the scenario's financial return to opening financial assets using a consistent monthly equivalent rate.
2. Add the configured monthly investment.
3. If step-up is enabled, increase the monthly investment by 6% each January after the first plan year.
4. Add monthly rent. Increase rent by its configured annual rate each January.
5. Reinvest rent before the passive-income start date.
6. Apply goal events due in the month at their inflation-adjusted cost.
7. For education and marriage, subtract the cost permanently from financial assets.
8. For the Bangalore house, subtract the cost from financial assets and add the same amount to future-house property value.
9. Apply real-estate appreciation to existing property, land, and the completed future house using a consistent monthly equivalent rate.
10. Record closing financial assets, property value, total net worth, contributions, rent, growth, and goal outflows.

The model must define and consistently test event ordering within a month. The implementation plan should use opening balance → growth → inflows → goal events → closing balance for financial assets, and document the equivalent ordering for property.

If a goal outflow exceeds available financial assets, financial assets may not silently become an implausible value. The scenario must record the goal as underfunded, retain the unmet amount as a shortfall, and continue projecting from a zero financial balance unless a later inflow restores it.

## Passive-income feasibility

At the 2029 target date calculate:

- Projected monthly rent.
- Monthly income gap: `max(0, target monthly income - monthly rent)`.
- Annual portfolio-income requirement: `monthly gap × 12`.
- Required financial corpus: `annual requirement / withdrawal rate`.
- Supported monthly portfolio income from projected financial assets.
- Total supported monthly passive income including rent.
- Surplus or shortfall against the required corpus.
- Whether funding this income would leave later linked goals protected in the same scenario.
- Earliest later month at which the income target becomes sustainable if 2029 is missed.

“On track” requires both income feasibility and protection of later enabled goals. Meeting the 2029 income number while causing a later education or marriage shortfall is not on track.

## Goal health

Each linked goal returns:

- Inflated cost at its due date.
- Projected available financial assets immediately before the event.
- Amount funded and shortfall.
- Status and explanatory reason.

Statuses:

- **Green:** fully funded in the expected scenario with a positive safety margin.
- **Amber:** funded with a narrow margin, or underfunded only in the conservative scenario.
- **Red:** underfunded in the expected scenario.

The exact amber safety-margin threshold is configurable at service level and must be fixed in tests; use 10% as the initial recommendation. The UI must show the reason in text and never rely on colour alone.

## Goals workspace layout

### 1. Pinned primary goal

Show ₹15 Cr by 2029, current net worth, achieved percentage, remaining amount, expected 2029 value, and the required monthly investment. Preserve existing goal editing and scenario behaviour while integrating it with the family plan.

### 2. Family wealth runway

Show a large annual chart spanning the current year through the final linked goal. Include:

- Financial assets.
- Property and land.
- Total net worth.
- Conservative, expected, and optimistic paths.
- Vertical event markers for both education goals, house construction, marriages, and the 2029 income target.
- Visible downward steps for permanent expenses.
- A transfer marker for the house asset conversion.
- Hover details for contributions, rent, investment growth, property growth, expenses, shortfalls, and closing wealth.

The chart uses the existing dashboard's clean line treatment without gradient area fill. Scenario lines and event types must have distinct, accessible colours and labels.

### 3. Goal health cards

Show one compact card per linked goal with due date, inflated cost, projected available wealth, funded percentage, surplus or gap, health status, and reason.

### 4. Passive-income panel

Show 2029 rent, required portfolio income, required corpus, supported monthly income, withdrawal rate, feasibility status, and whether later goals remain protected.

### 5. Scenario comparison

Compare conservative, expected, and optimistic end values, 2029 target result, passive-income result, and the first underfunded linked goal.

### 6. Assumptions drawer

Allow editing of monthly investment, annual step-up checkbox and percentage, return rates, goal inflation, rent, rent growth, rent reinvestment, property appreciation, and withdrawal rate. Draft changes update a local projection preview; Save persists the complete configuration atomically. Restore Defaults reinstates the approved defaults only after confirmation.

## Persistence and API boundaries

Persist three concepts separately:

1. Family-plan settings, including rent, contributions, step-up, withdrawal, and property assumptions.
2. Linked goals and their funding treatment.
3. Ordered scenario settings.

Projection results are derived on demand from the latest immutable portfolio snapshot and the persisted plan. They are not stored as authoritative balances.

API capabilities:

- Load the complete family plan, projections, goal health, and passive-income analysis.
- Atomically update all assumptions and linked goals.
- Restore approved defaults.
- Return field-specific validation errors.

The existing primary-goal API may remain for compatibility, but the family-plan response becomes the Goals workspace's consolidated read model.

## Validation and failure behaviour

- Reject invalid or past target dates where the goal type requires a future date.
- Reject negative amounts, returns outside safe configured bounds, zero or negative withdrawal rates, and non-finite calculations.
- Reject duplicate linked-goal identifiers and unsupported funding treatments.
- Enforce the safe projection horizon.
- A failed update rolls back the entire family-plan change.
- A failed workbook import leaves both portfolio snapshots and family-plan settings unchanged.
- Empty portfolio data produces an explicit import call-to-action; it does not display invented projections.
- Underfunded goals are projection results, not request-validation failures.

## Testing strategy

### Calculation tests

- Monthly compounding and January annual summaries.
- Flat ₹6 lakh contribution.
- Optional 6% January step-up.
- Rent reinvestment and 6% annual rent growth.
- Inflation-adjusted linked-goal costs.
- Education and marriage permanent outflows.
- House financial-to-property conversion with no artificial net-worth loss.
- Multiple events in the same month.
- Underfunded goal continuation and shortfall reporting.
- Passive-income corpus, rental offset, and later-goal protection.
- Conservative, expected, and optimistic isolation.
- Non-finite and unsafe-horizon rejection.

### Persistence and API tests

- Default seed is deterministic.
- Complete configuration update is atomic.
- Invalid update preserves prior settings.
- Workbook refresh changes projection starting values without changing assumptions.
- Restore Defaults produces the approved configuration.
- Field-specific errors use stable locations.

### Frontend tests

- Primary goal remains pinned.
- Runway series and event markers map correctly.
- Goal status includes textual reasons.
- Step-up checkbox controls the percentage input and preview.
- Unsaved changes, save, retry, and restore flows.
- Empty, loading, warning, and error states.
- Desktop and tablet rendering without horizontal overflow.

## Deferred scope

- Monte Carlo simulation.
- Salary and tax modelling.
- SGD/INR/USD sensitivity.
- ETF domicile and estate-tax analysis.
- Estate allocation and inheritance projections.
- Market-crash simulation.
- Automated investment or broker orders.

These are future extensions and must not complicate the first family-runway implementation.

## Acceptance summary

The enhancement is successful when the user can change the ₹6 lakh monthly investment, optionally apply a 6% annual step-up, edit every linked goal and assumption, and immediately understand from one runway whether ₹15 Cr and ₹2 lakh monthly passive income are achievable by 2029 without sacrificing later family goals.
