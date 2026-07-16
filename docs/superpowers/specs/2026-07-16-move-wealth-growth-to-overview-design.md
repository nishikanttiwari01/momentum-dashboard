# Move Wealth Growth to Overview Design

## Goal

Show the existing `PortfolioWealthGrowth` chart on the Overview tab and remove the dummy wealth-growth chart currently rendered there.

## Changes

- Render `PortfolioWealthGrowth` in `PortfolioOverview` in place of its local sample `wealthHistory` chart.
- Remove `PortfolioWealthGrowth` from the Investments panel in `Portfolio.tsx`.
- Keep the mutual-fund allocation panel, asset panels, balance sheet, investments, goals, and import behaviour unchanged.
- Let the remaining mutual-fund allocation panel use the available width on Investments.

## Verification

- Assert Overview contains `portfolio-wealth-growth` exactly once.
- Assert the Investments panel no longer renders that chart.
- Run focused portfolio tests and the frontend build.
