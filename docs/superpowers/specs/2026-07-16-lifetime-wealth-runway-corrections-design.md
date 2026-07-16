# Lifetime Family Wealth Runway Corrections

Date: 2026-07-16

## Objective

Correct the Family Wealth Runway so it uses the complete household balance sheet, represents rent accurately, projects through age 80, and lets the user compare independently configurable financial and property assumptions. Preserve all existing Portfolio-page capabilities.

## Authoritative workbook data

`investment.xlsx` remains the import source. The latest populated `BALANCE SHEET` column is authoritative for aggregate household totals:

- Financial/current-assets market value: ₹4,46,58,852.25.
- Fixed/property-assets market value: ₹3,84,00,000.
- Combined net-worth market value: ₹8,30,58,852.25.
- Combined invested capital: ₹5,86,63,055.25.

The latest `FIXED ASSET` values provide the property components:

- Brigade land: ₹2,16,00,000 market value.
- Amrapali flat: ₹68,00,000 market value.
- Gera office: ₹1,00,00,000 market value.

The initial monthly rent comes from the workbook income data:

- Gera office: ₹30,000.
- Amrapali flat: ₹14,000.
- Total starting rent: ₹44,000 per month.

The importer must reconcile aggregate totals against components and warn on discrepancies. It must not double-count components already represented by an aggregate. Imported values are editable through dated app overrides. Later workbook imports update workbook-sourced values while preserving explicit overrides.

## Starting wealth and the primary goal

The ₹15 Cr primary goal includes both financial and fixed/property assets. Every projection starts with ₹4.47 Cr financial assets and ₹3.84 Cr property assets, for combined net worth of ₹8.31 Cr. The progress header must use combined market value and show combined invested capital.

The primary milestone remains ₹15 Cr on 31 December 2029. It is a prominent milestone within the lifetime projection rather than the end of the chart. The UI shows progress, projected value, surplus or shortfall, and on-track status for each scenario at that date.

## Lifetime projection

The configurable birth month defaults to July 1984. The configurable projection end age defaults to 80, producing a default end date in July 2064. Important chart labels show calendar year and approximate age.

Monthly investment defaults to ₹6,00,000. The optional annual step-up defaults to 6%. Each scenario has a configurable contribution stop age, default 60. After that age, contributions stop but financial growth, property growth, rental income, withdrawals and goal events continue through age 80.

Existing education, house, marriage and passive-income goals remain dated milestone events. The December 2029 ₹15 Cr target is visually stronger than secondary milestones.

Cash-funded goals use financial assets only. When an education, marriage or other expense milestone is reached, its funded amount is deducted from available financial assets. Existing property assets are never reduced, sold or treated as cash unless the user later records an explicit property-sale event. If financial assets cannot fully fund the goal, financial assets stop at zero and the unfunded balance is reported as a shortfall; property remains unchanged. The lifetime runway continues from those post-event balances.

## Property treatment

The property series starts immediately at ₹3.84 Cr and grows every projection year. A single property-growth rate applies to the combined property portfolio within each scenario.

The future Bangalore-house asset-conversion event transfers the funded amount from financial assets into property assets. It changes asset composition but does not create net worth or represent the first property holding. Goal shortfalls remain explicit.

The Bangalore-house conversion is also limited by available financial assets. It may transfer only the funded amount into property; any unfunded portion remains a visible shortfall. Existing property holdings cannot be liquidated automatically to fund the conversion.

## Rental treatment

The projection distinguishes:

- Rent received: gross annual rental income, which continues growing throughout the projection.
- Rent reinvested: the portion added to financial assets through the configured reinvestment cutoff.

After the cutoff, rent received continues and remains visible, while rent reinvested becomes zero. Rent that is not reinvested does not silently increase investment assets. Tooltips and the passive-income panel show the distinction.

## Scenario configuration

Retain three scenarios: Conservative, Expected and Optimistic. Use a compact comparison matrix with one column per scenario and aligned rows for:

- Financial-assets annual return.
- Property annual growth.
- Monthly investment.
- Annual investment step-up and enabled state.
- Contribution stop age.
- Calculated ending net worth at age 80.
- Calculated December 2029 goal status.

All assumption values are manually editable. One Save and recalculate action persists the matrix atomically. Draft values remain visibly distinct from the last saved calculation. The existing assumptions drawer remains for rent, reinvestment, withdrawal, safety margin and linked-goal details.

## Chart interaction

The line-only, no-gradient chart extends through age 80 and offers two modes:

1. Composition mode selects one scenario and shows total net worth, financial assets and property assets.
2. Compare scenarios mode shows only the three total-net-worth scenario lines.

This prevents five competing lines from obscuring interpretation. The chart must remain responsive without horizontal page overflow.

The tooltip shows:

- Calendar date and age.
- Total net worth.
- Financial assets.
- Property assets.
- Annual contribution.
- Rent received.
- Rent reinvested.
- Financial growth.
- Property growth.
- Goal withdrawals and asset-conversion events.

The chart retains an accessible semantic annual-data table and milestone descriptions.

## Text and encoding correction

Scan the Portfolio UI and affected API defaults for mojibake such as `â‚¹`, `Â·` and related sequences. Replace corrupted literals with correct UTF-8 characters or stable formatting functions. The corrected header reads:

- Net worth market value
- ₹8.31 Cr
- Combined household value · property included
- Invested capital ₹5.87 Cr

No corrupted characters may remain in rendered Portfolio content or tests.

## Backend and persistence changes

Extend the stored family plan and API contracts with:

- Birth month/year.
- Projection end age.
- Per-scenario financial return.
- Per-scenario property growth.
- Per-scenario monthly contribution.
- Per-scenario step-up configuration.
- Per-scenario contribution stop age.
- Separate annual rent received and rent reinvested values.
- December 2029 milestone result.

Add a forward migration with canonical defaults and safe upgrade behavior for existing databases. Family-plan writes remain atomic and restore-default behavior includes the new values.

## Validation and error handling

- Validate dates, ages, contribution stop age and projection end age consistently.
- Validate financial and property return ranges separately.
- Reject invalid scenario matrices atomically with field-addressable errors.
- Show an import/reconciliation warning instead of silently replacing missing property or rent with zero.
- Preserve the last saved calculation while edits are dirty or a recalculation fails.
- Continue using loading, empty, retry and import states without fabricated estimates.

## Verification

Automated coverage must include:

- Workbook extraction and reconciliation of the stated balance-sheet, fixed-asset and rental values.
- No aggregate/component double-counting.
- Database migration and default restoration.
- Projection from July 1984 through age 80.
- December 2029 ₹15 Cr milestone values and status.
- Contributions stopping at age 60 by default.
- Existing property growth from the first projection year.
- Rent received continuing after rent reinvestment stops.
- Bangalore-house asset conversion preserving total value before costs/shortfall.
- Education, marriage and other expense goals deducting only financial assets, never property.
- Insufficient financial assets flooring at zero and producing a shortfall while property remains unchanged.
- Independent scenario financial/property assumptions.
- Atomic scenario edits and field errors.
- Composition and comparison chart modes.
- Correct UTF-8 rendering and absence of known mojibake sequences.
- Responsive desktop and tablet rendering with no clipped chart or horizontal overflow.
- Regression coverage for existing Portfolio import, transaction, mutual-fund chart and sorting behavior.

## Out of scope

- Per-property growth rates.
- New property-calculator or remittance modules.
- Reintroducing discontinued mutual-fund sheets.
- Automatic live property valuations.
