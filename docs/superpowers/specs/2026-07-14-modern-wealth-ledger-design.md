# Modern Wealth Ledger — Portfolio UI Design

## Objective

Redesign the complete Portfolio page as a polished Indian wealth-management dashboard while preserving every existing behavior. The page must make crore-scale wealth, asset allocation, historical growth, mutual-fund holdings, NAV decisions and transactions faster to understand.

## Scope

The visual upgrade applies to the complete Portfolio page:

- Portfolio summary
- Allocation by category
- Wealth growth over years
- Current assets and fixed assets
- Year-wise balance sheet
- Accumulation signals
- Indian mutual-fund holdings and expanded NAV histories
- QQQ holdings and transactions

All existing actions and data behavior remain in place, including NAV refresh, period selection, purchase markers, average NAV, expandable fund rows, transaction entry, transaction tables and CSV-backed data.

## Reference Principles

The design adapts three established portfolio-dashboard patterns:

- Consolidated reporting and analytics from Zerodha Console
- Allocation-first portfolio understanding from Empower
- Friendly restraint associated with Indian retail investment products such as Groww

The result is not a visual copy. It is tailored to the workbook data, Indian number formatting and the existing application shell.

## Visual Direction

Name: **Modern Wealth Ledger**

The interface combines the clarity of an investment ledger with approachable wealth-management visuals. It uses meaningful financial icons, crore-first values, calm blue and emerald accents, and chart fills that communicate growth without resembling a trading terminal.

### Tokens

| Role | Value |
|---|---|
| Ledger blue | `#2E7CF6` |
| Wealth emerald | `#12B76A` |
| Allocation cyan | `#06AED4` |
| Property amber | `#F79009` |
| Primary ink | `#14213D` |
| Canvas | `#F5F7FC` |
| Muted text | `#667085` |
| Divider | `#E4E7EC` |

The existing application font remains to avoid visual conflict with the rest of the product. Typography gains three roles: compact uppercase section labels, prominent tabular financial values and quiet explanatory captions.

### Signature Element

The wealth-growth visualization is a blue-to-emerald gradient area chart. Each annual market-value point displays a direct `₹x.xx Cr` label. The latest point receives stronger emphasis. Principal remains visible as a muted dashed comparison line so growth is readable without a tooltip.

## Icon Language

Icons communicate asset type or action and are not decorative:

- Mutual funds: account balance or wallet
- Stocks: candlestick or trending chart
- Debt and savings: savings vault
- Land and residential property: home or landscape
- Office property: business building
- Allocation: donut chart
- Wealth growth: rising portfolio
- Transactions: receipt or timeline
- Accumulation signal: opportunity or status icon

Icons appear in subtly tinted tiles. They are not repeated beside every small label.

## Layout

```text
Portfolio summary with icon-led financial metrics
┌ Allocation ─────────┬ Wealth growth area chart ─────────────┐
├ Current assets ─────┼ Fixed assets ─────────────────────────┤
├ Balance-sheet table ┴ Principal vs market-value chart ──────┤
├ Accumulation opportunities ─────────────────────────────────┤
├ Mutual-fund holdings and expandable NAV charts ─────────────┤
└ QQQ holdings and transaction history ───────────────────────┘
```

Desktop keeps the compact two-column overview. Tablet and mobile stack panels without horizontal overflow. Detailed tables remain horizontally scrollable only where their column count requires it.

## Component Design

### Summary

The summary becomes a group of distinct metric tiles for invested amount, current market value, absolute return and XIRR. Each tile uses one meaningful icon, a compact label and a prominent tabular value. Refresh NAV remains clearly accessible.

### Allocation

The compact donut and category ledger remain. Spacing, icon-led heading and color hierarchy are refined without expanding the card width.

### Wealth Growth

Replace the market-value line with an area series and gradient fill. Show point labels in crores and keep the principal comparison line muted and dashed. The tooltip displays series name and `₹x.xx Cr`. Disable animation where it interferes with deterministic rendering or screenshots.

### Asset Panels

Each asset row receives an icon based on its asset type. Principal, market value and gain retain tabular alignment. Positive gains use emerald; neutral values use muted ink.

### Balance Sheet

Preserve the table. Improve the grouped bar chart with direct crore labels, clearer contrast and a concise tooltip. Principal remains visually secondary to market value.

### Accumulation Signals

Present signals as compact opportunity rows or cards with a meaningful status icon, fund name and reason. Preserve the current rule text and status colors.

### Mutual Funds and QQQ

Apply the same section-heading, card and action-button language to detailed holdings. Preserve row expansion, all NAV ranges, chart markers, average NAV, add-transaction dialogs and data tables.

## Data and Behavior

This is a presentation-layer change. No API response shape, workbook value, transaction calculation, NAV calculation or persistence behavior changes. Existing loading, empty and error logic remains; only compatible styling may be added.

## Accessibility and Responsive Behavior

- Icons that repeat visible text are hidden from assistive technology.
- Icon-only controls retain accessible names and visible keyboard focus.
- Color is never the only indicator of gain, loss or status.
- Financial values use tabular numerals where supported.
- Reduced-motion preferences are respected.
- The overview stacks at tablet and mobile widths.
- Tables do not force the page viewport to overflow.

## Testing and Acceptance Criteria

Implementation follows test-driven development.

1. The wealth chart renders an area series with direct `₹x.xx Cr` labels.
2. Principal renders as a visually secondary comparison series.
3. Overview and asset sections render meaningful icons with accessible text.
4. Existing portfolio component tests continue to pass.
5. The production frontend build succeeds.
6. Desktop browser rendering confirms balanced card widths, complete charts and readable labels.
7. Mobile browser rendering confirms stacked cards, usable actions and no page-level horizontal overflow.
8. Existing fund expansion, time ranges, transaction markers, average NAV, refresh and transaction-entry actions remain present and functional.

## Out of Scope

- Backend or workbook-import changes
- New investment calculations
- New portfolio recommendations
- Changes to transaction persistence
- Redesigning pages outside Portfolio
