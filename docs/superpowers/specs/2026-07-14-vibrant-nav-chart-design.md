# Vibrant Mutual-Fund NAV Chart Design

## Objective

Make every Indian mutual-fund NAV chart visually engaging and faster to interpret while preserving its range controls, average NAV, purchase markers, inception date, returns, transaction table and data calculations.

## Direction

Use a saturated blue-to-violet NAV line with a translucent gradient area fill. The visual language must match the Modern Wealth Ledger portfolio overview without turning the chart into a trading-terminal display.

## Visual Treatment

- NAV line: strong blue `#2E7CF6` transitioning visually toward violet `#7A5AF8`.
- Area fill: translucent blue/violet gradient fading into the chart background.
- Below-average zone: quiet emerald tint `#12B76A` to indicate historically lower-than-average NAV.
- Average NAV: violet dashed reference line with a compact label badge.
- Purchases: amber `#F79009` dots with white border, soft glow and detailed tooltip.
- Latest NAV: larger blue marker with a compact value badge.
- Grid: faint dashed blue-grey lines.
- Chart container: white rounded surface, subtle lavender border glow and adequate internal padding.
- Header metrics: compact colored badges for selected-period return, inception date and latest-vs-average percentage.

Red is reserved for negative return text. It is not used as the primary line color because the NAV series itself is not an error state.

## Interactions and Data

Existing behavior remains unchanged:

- 1M, 6M, 1Y, 5Y and since-inception ranges
- Correct date filtering and Y-axis domains
- Purchase markers and transaction tooltips
- Average NAV reference
- Transaction history table
- Expanded-row behavior

The chart animation is disabled or minimized where it could produce incomplete screenshots or misleading transitions.

## Component Boundary

The change remains inside `FundNavChart` in `frontend/src/pages/Portfolio.tsx`, with focused helpers extracted only if required for gradient IDs or labels. No API or backend changes are needed.

## Validation

1. A regression test requires an area series, gradient definition, average reference and latest-value marker.
2. Existing chart-data and Portfolio tests remain green.
3. The production build succeeds.
4. The expanded mutual-fund chart is rendered in a browser at 1Y and 5Y ranges.
5. Visual inspection confirms a complete area fill, purchase dots, readable badges and no chart clipping.
