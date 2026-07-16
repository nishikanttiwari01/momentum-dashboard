# Compact Scenario Matrix Design

Date: 2026-07-16

## Goal

Replace the oversized scenario inputs with a compact, comparison-first editor positioned directly beneath the Family Wealth Runway chart.

## Placement

The Goals workspace order is:

1. Primary ₹15 Cr progress.
2. Family Wealth Runway chart.
3. Compact Scenario comparison editor.
4. Goal-health cards.
5. Passive-income analysis.
6. Remaining assumptions and supporting sections.

This keeps scenario controls next to the graph they recalculate.

## Desktop layout

Retain a matrix with one left label column and Conservative, Expected and Optimistic columns. Numeric controls use fixed compact widths rather than stretching to fill each scenario column. Row labels appear only on the left; inputs do not repeat floating labels.

Rows are financial return, property growth, monthly investment, annual step-up, step-up percentage and contribution stop age. Inputs show concise suffixes such as `%`, `₹L/month` and `age`. Annual step-up uses a small switch with its percentage control beside it.

Each scenario ends with a lightly tinted summary block containing ending net worth at age 80 and December 2029 ₹15 Cr status. Save and recalculate is a compact header action and remains disabled when no draft changes exist.

## Mobile layout

Below the desktop breakpoint, render one compact scenario card at a time or stacked cards. The page must not horizontally overflow. Each card contains the same assumptions and result summary with labels shown once.

## Copy and accessibility

Remove all mojibake, including `Â·`, `â‚¹` and broken ellipsis sequences. Inputs retain accessible labels through `aria-label` even when visible floating labels are removed. Keyboard access, validation messages, disabled state, dirty-state warning and save behavior remain intact.

## Verification

- Render tests assert the scenario editor follows the chart and precedes goal cards.
- Desktop styles assert compact fixed-width controls and no stretching.
- Mobile styles assert stacked cards/no page overflow.
- Interaction tests preserve scenario edits, step-up behavior, field errors and save payload.
- Source/render tests reject known mojibake sequences.
- Full frontend tests and production build must pass.
