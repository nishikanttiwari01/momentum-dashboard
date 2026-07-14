# Century Ply-Style Mutual-Fund NAV Chart Design

## Objective

Make every Indian mutual-fund NAV chart faster to interpret by adopting the clean line-chart layout already used for Century Ply, while preserving its range controls, average NAV, purchase markers, inception date, returns, transaction table and data calculations.

## Direction

Use the existing Century Ply chart as the visual reference: a crisp blue line on white, restrained axes, faint horizontal grid lines and minimal annotation. Do not use an area or gradient fill.

## Visual Treatment

- NAV line: Century Ply blue `#2E90FA`, approximately `1.8px` wide, with no area or gradient fill.
- Plot background: plain white with no tinted zones, glow or decorative backdrop.
- Average NAV: grey dashed reference line, matching the Century Ply entry-price reference, with a small right-aligned label.
- Purchases: green `#00B386` dots with a white border and the existing detailed transaction tooltip.
- Latest NAV: a small blue marker and compact value label that remain inside the plot bounds.
- Grid: very faint solid horizontal lines (`#F5F5F5`); no vertical grid lines.
- Axes: compact muted-grey labels, no tick marks and subtle axis lines.
- Chart container: minimal white surface with comfortable internal spacing and no lavender glow.
- Header metrics: keep the existing return, inception and latest-vs-average information, using restrained text color rather than prominent badges.

Red remains reserved for negative return text. It is not used as the primary line color because the NAV series itself is not an error state.

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

The change remains inside `FundNavChart` in `frontend/src/pages/Portfolio.tsx`, with focused helpers extracted only if required for marker or reference labels. No API or backend changes are needed.

## Validation

1. A regression test requires the clean line series, horizontal grid, average reference, purchase markers and latest-value marker, and rejects an area/gradient series.
2. Existing chart-data and Portfolio tests remain green.
3. The production build succeeds.
4. The expanded mutual-fund chart is rendered in a browser at 1Y and 5Y ranges.
5. Visual inspection confirms there is no area or gradient fill, and that the blue line, green purchase dots, references and labels are readable without chart clipping.
