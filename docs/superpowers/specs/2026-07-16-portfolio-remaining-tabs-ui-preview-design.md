# Portfolio Remaining Tabs UI Preview Design

## Goal

Replace the empty Overview, Annual Review, and Properties & Rent tabs with a fast, visually complete UI preview. Use clearly labelled sample data so layout and analysis can be reviewed before backend integration.

## Scope

- Build UI only; no API, database, or workbook changes.
- Preserve the existing Investments, Goals, and Data Import tabs and their behaviour.
- Add a visible `UI preview · sample data` badge to every mock-data tab.
- Keep the dashboard compact, responsive, and consistent with the existing Modern Wealth Ledger styling.

## Tab Design

### Overview

- Compact net-worth summary strip showing total net worth, invested capital, gains, and combined India/US exposure.
- Asset-allocation donut with category amounts and percentages.
- Three-year wealth-growth area chart comparing market value with invested capital.
- Geographic allocation for India and US holdings, designed to allow more markets later.
- Short insight cards for strongest contributor, concentration risk, and next review action.

### Annual Review

- Calendar-year selector using January through December reporting.
- Summary metrics for opening value, contributions, investment gains, property growth, closing value, and annual XIRR.
- Waterfall-style visual showing how opening wealth becomes closing wealth.
- Year-by-year table for fast comparison of cash deployed, gains, closing wealth, and XIRR.

### Properties & Rent

- Property cards for the currently understood holdings: Brigade land, Amrapali flat, and Gera office.
- Each card shows principal, current market value, appreciation, monthly/annual rent, occupancy, and rental yield.
- Portfolio-level value-growth and rental-income charts.
- Rental-yield comparison to make weak and strong income assets obvious.

## Visual Direction

Use a disciplined wealth-ledger layout: white surfaces, compact spacing, strong navy text, saturated blue/teal/violet data colours, and amber only for attention states. Charts should carry the visual interest; cards remain quiet. Currency labels use correct UTF-8 rupee and crore formatting.

The signature element is the annual wealth bridge: a compact visual explanation of how contributions, market gains, property growth, and withdrawals produced the year-end result.

## Component Boundaries

- `PortfolioOverview.tsx`: overview-only mock dataset and presentation.
- `PortfolioAnnualReview.tsx`: year review mock dataset, selector, bridge, and table.
- `PortfolioPropertiesRent.tsx`: property mock dataset, cards, and property charts.
- `PortfolioHub.tsx`: tab routing only; existing functional tab nodes remain unchanged.

## Interaction and States

- Charts and cards resize for desktop and mobile.
- Year selection updates the Annual Review summary from local sample records.
- Sample-data labels prevent preview figures from being mistaken for imported portfolio values.
- No edit or save actions are included until the user approves the UI and backend mapping is designed.

## Verification

- Add focused tab-rendering coverage to confirm all three placeholders are replaced and existing functional tabs still render.
- Run the focused frontend test and a production build only; broader backend testing is intentionally deferred because this phase is UI-only.

## Out of Scope

- Workbook mapping, persistence, API contracts, live rental calculations, and backend validation.
- Changes to mutual-fund transaction charts, goal calculations, imports, or existing investment functions.
