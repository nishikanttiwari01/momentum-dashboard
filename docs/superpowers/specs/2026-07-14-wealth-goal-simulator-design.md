# Wealth Goal Simulator Design

## Purpose

Activate the Portfolio **Goals** tab as a decision tool for the household's primary target: a nominal consolidated net worth of ₹15 Cr by 31 December 2029. Progress uses the latest consolidated net-worth market value, including investments, cash/debt, US holdings converted to INR, and property. Goal projections are planning scenarios only and never mutate imported portfolio records.

## Scope

The first delivery supports one persisted primary goal and three persisted scenarios. It includes:

- current progress, achieved percentage, remaining amount, and deadline;
- expected deadline value and projected completion date;
- required monthly contribution under the expected-return assumption;
- conservative, expected, and optimistic projections;
- editable target, deadline, annual returns, and monthly contributions;
- a required-versus-projected trajectory chart;
- database persistence across browsers and devices;
- loading, empty, validation, save-error, and saved states.

Secondary workbook goals, timeline events, inflation adjustment, Monte Carlo simulation, asset-class-specific return models, and automated investment recommendations are deferred.

## Defaults

- Goal name: `₹15 Cr by 2029`
- Target: ₹15,00,00,000
- Deadline: 31 December 2029
- Conservative annual return: 7%
- Expected annual return: 10%
- Optimistic annual return: 13%
- Monthly contribution: configurable independently for each scenario, initially ₹0

The UI provides **Restore defaults**, but restoration is not persisted until the user saves.

## Architecture

### Persistence

Add a `wealth_goals` table for the primary target and a `wealth_goal_scenarios` table for its three named scenarios. The migration seeds the default primary goal and scenarios. The goal is marked primary so later deliveries can add secondary goals without changing the API contract.

Stored goal fields include name, target amount in INR, deadline, primary flag, created time, and updated time. Stored scenario fields include scenario key, annual return percentage, monthly contribution in INR, display order, created time, and updated time.

### Backend API

Extend the wealth-portfolio API with:

- `GET /api/v1/wealth-portfolio/goals/primary` — returns persisted settings plus calculated progress and projections using the latest portfolio snapshot;
- `PUT /api/v1/wealth-portfolio/goals/primary` — validates and atomically updates the goal and all three scenarios, then returns the recalculated response.

The PUT request replaces the complete editable configuration. Partial scenario sets are rejected so the application cannot persist an ambiguous simulator state.

### Calculation service

A dedicated goal service owns every formula. The UI renders returned values and does not independently implement financial calculations.

The starting value is `net_worth_market_value_inr` from the latest wealth summary. Scenario values compound monthly:

`next balance = current balance × (1 + annual return / 12) + monthly contribution`

Annual return percentages are converted to decimal rates before calculation. The deadline projection uses the number of whole monthly periods from the calculation date to the deadline. The trajectory returns a compact monthly series suitable for charting.

The required trajectory compounds from the current value to the target using the expected scenario's return and the mathematically required monthly contribution. Required monthly contribution is ₹0 when the starting value alone reaches the target under the expected return. When a positive contribution cannot be calculated because the deadline has passed or inputs are invalid, the API returns a validation error rather than a fabricated value.

Projected completion date is the first month-end when the scenario balance reaches the target, searched to a bounded horizon of 50 years. If it is not reached within the horizon, the value is `null` and the UI says `Beyond projection horizon`.

### Validation

- Target must be greater than zero.
- Deadline must be later than the calculation date.
- Annual returns must be between -25% and 50%.
- Monthly contributions must be zero or greater.
- Exactly one conservative, expected, and optimistic scenario must be supplied.
- Scenario return order must remain conservative ≤ expected ≤ optimistic.

Validation errors are field-addressable so the form can place messages beside the relevant input.

## API response

The primary-goal response contains:

- persisted goal and scenario settings;
- calculation date and latest snapshot identifier;
- current net worth, achieved percentage, and remaining amount;
- required expected-scenario monthly contribution;
- required trajectory points;
- for each scenario: projected deadline value, surplus or shortfall, on-track state, projected completion date, and trajectory points;
- data-health state: `empty`, `fresh`, `warning`, or `unavailable`.

When no portfolio snapshot exists, persisted settings are still editable, while calculated monetary results and trajectories are `null`/empty. The UI directs the user to import `investment.xlsx` from Data Import.

## User interface

### Finish-line panel

The page opens with a wide primary-goal card showing target, current net worth, deadline, achieved percentage, and remaining amount. A segmented horizontal progress track is the visual signature. It clamps visual fill at 100% while the numeric achieved percentage may exceed 100%.

Four compact metrics below the track show:

1. amount remaining;
2. required monthly investment under the expected return;
3. expected value at the deadline;
4. expected projected completion date.

### Projection workspace

On desktop, the trajectory chart occupies the larger left column and configuration occupies the right column. On tablet and mobile they stack without horizontal page overflow.

The chart uses direct endpoint labels and four unfilled lines: required trajectory, conservative, expected, and optimistic. Colors are restrained amber, blue, emerald, and slate. Tooltips show date and Indian-formatted currency. The chart respects reduced-motion preferences.

The configuration form edits target, deadline, three return rates, and three monthly contributions. Unsaved changes are visible. **Save changes** persists atomically; **Restore defaults** modifies the form only. Inputs have explicit labels and keyboard-accessible focus states.

### Scenario cards

Three cards summarize deadline value, surplus/shortfall, contribution, return assumption, on-track status, and projected completion date. Status is communicated by text and icon as well as color.

## Error and state handling

- Loading uses stable skeletons matching the final card dimensions.
- No snapshot shows an import call-to-action while leaving configuration editable.
- GET failure shows a retry action and does not substitute placeholder wealth values.
- Field validation is displayed inline and preserves unsaved form values.
- Save failure leaves the form dirty and provides a retry action.
- Successful save refreshes the shared goal query and displays a concise saved confirmation.
- Stale or fallback wealth data is labeled without blocking simulation.

## Integration

`PortfolioHub` renders the new goal workspace for the Goals tab while preserving Investments and Data Import behavior. The goal query uses React Query and a stable shared key so a later Overview progress card can consume the same response. No goal component parses workbook data directly.

## Testing

Backend tests cover migration defaults, validation, monthly compounding, required-contribution edge cases, completion-date bounds, empty snapshots, API retrieval, atomic updates, and persisted reloads.

Frontend tests cover tab activation, loading/empty/error states, Indian currency formatting, progress clamping, form edits, validation display, save/restore behavior, scenario status, and responsive source constraints. A production build and browser render at desktop and tablet widths are required before completion.

