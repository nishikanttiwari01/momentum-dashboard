# Century Ply-Style Mutual-Fund Chart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle every expanded Indian mutual-fund NAV chart as a clean Century Ply-style blue line chart without an area or gradient fill.

**Architecture:** Keep all chart data, range selection, transaction overlays and rendering inside the existing `FundNavChart` component. Replace only the decorative Recharts layers and styles, and protect the intended visual contract with the existing source-level Vitest regression test.

**Tech Stack:** React, TypeScript, Material UI, Recharts, Vitest, Vite

---

## File Structure

- Modify `frontend/src/features/portfolio/FundNavChartStyle.test.ts`: define the clean line-chart visual contract and explicitly reject gradient area rendering.
- Modify `frontend/src/pages/Portfolio.tsx`: remove the area layer and gradient definition; align the line, grid, axes, reference line, markers and container with the Century Ply chart.

### Task 1: Lock the clean line-chart contract

**Files:**
- Modify: `frontend/src/features/portfolio/FundNavChartStyle.test.ts`

- [ ] **Step 1: Replace the gradient expectations with the clean-line expectations**

```ts
describe('FundNavChart visual treatment', () => {
  it('renders a clean Century Ply-style NAV line with transaction references', () => {
    const source = readFileSync(new URL('../../pages/Portfolio.tsx', import.meta.url), 'utf8');
    expect(source).toContain('data-testid="fund-nav-chart"');
    expect(source).toContain('stroke="#2E90FA"');
    expect(source).toContain('stroke="#F5F5F5"');
    expect(source).toContain('vertical={false}');
    expect(source).toContain('Average NAV');
    expect(source).toContain('Latest NAV');
    expect(source).toContain("fill=\"#00B386\"");
    expect(source).not.toContain('<Area ');
    expect(source).not.toContain('navAreaGradient');
  });
});
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `npm test -- --run src/features/portfolio/FundNavChartStyle.test.ts`

Expected: FAIL because the component still contains `<Area>`, `navAreaGradient`, the old blue line and amber transaction markers.

- [ ] **Step 3: Commit the failing regression test**

```bash
git add frontend/src/features/portfolio/FundNavChartStyle.test.ts
git commit -m "test: define clean mutual fund nav chart style"
```

### Task 2: Implement the Century Ply chart treatment

**Files:**
- Modify: `frontend/src/pages/Portfolio.tsx:24-260`

- [ ] **Step 1: Remove the area-chart import and generated gradient identifier**

Delete `Area` from the Recharts import, delete `navGradientId`, and remove the `<defs>`, `<linearGradient>` and `<Area>` elements from `FundNavChart`.

- [ ] **Step 2: Apply the clean plot and axis styling**

Use the existing Century Ply values:

```tsx
<CartesianGrid stroke="#F5F5F5" vertical={false} />
<XAxis tick={{ fontSize: 10, fill: '#9b9b9b' }} tickLine={false} axisLine={{ stroke: '#ECECEC' }} />
<YAxis tick={{ fontSize: 10, fill: '#9b9b9b' }} tickLine={false} axisLine={{ stroke: '#ECECEC' }} />
<Line type="monotone" dataKey="nav" stroke="#2E90FA" strokeWidth={1.8} dot={false} isAnimationActive={false} />
```

Remove the lavender glow and tinted chart background from the surrounding chart box, leaving a plain white plot with the existing responsive height and spacing.

- [ ] **Step 3: Restyle reference and transaction markers**

Render purchase `ReferenceDot` elements with `fill="#00B386"`, white borders and no drop-shadow. Render the average line with `stroke="#B0B4BE"`, `strokeDasharray="5 4"` and its existing `Average NAV` label. Keep the latest NAV marker blue and ensure its label remains inside the right edge.

- [ ] **Step 4: Run the focused test and verify it passes**

Run: `npm test -- --run src/features/portfolio/FundNavChartStyle.test.ts`

Expected: 1 test passes.

- [ ] **Step 5: Commit the implementation**

```bash
git add frontend/src/pages/Portfolio.tsx
git commit -m "feat: use clean line charts for mutual fund nav"
```

### Task 3: Verify behavior and rendered output

**Files:**
- Verify: `frontend/src/pages/Portfolio.tsx`
- Verify: `frontend/src/features/portfolio/FundNavChartStyle.test.ts`

- [ ] **Step 1: Run portfolio tests**

Run: `npm test -- --run src/features/portfolio`

Expected: all portfolio tests pass.

- [ ] **Step 2: Run the production build**

Run: `npm run build`

Expected: TypeScript and Vite build complete successfully.

- [ ] **Step 3: Render the application and inspect a mutual-fund 1Y chart**

Start the existing local frontend, open Portfolio, expand an Indian mutual fund, select `1Y`, and capture the rendered chart. Confirm a complete blue line, white background, subtle horizontal grid, green purchase dots, readable average/latest labels and no area fill.

- [ ] **Step 4: Inspect the same mutual-fund 5Y chart**

Select `5Y` and capture the rendered chart. Confirm the full five-year series renders without vertical spikes, clipping, gradient fill or missing labels.

- [ ] **Step 5: Record verification in the implementation commit if adjustments were needed**

```bash
git add frontend/src/pages/Portfolio.tsx frontend/src/features/portfolio/FundNavChartStyle.test.ts
git commit -m "fix: refine mutual fund nav chart rendering"
```

Skip this commit when browser verification requires no further changes.
