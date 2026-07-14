# Portfolio Workbook Dashboard Mockup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-contained HTML mockup showing the approved current-portfolio dashboard and Excel refresh preview without changing application code.

**Architecture:** One standalone file contains semantic HTML, responsive CSS, inline SVG charts, and minimal JavaScript for tabs and a simulated local `.xlsx` validation preview. A small PowerShell validation script tests the static artifact for required sections, privacy exclusions, and balanced totals; browser rendering provides the final visual check.

**Tech Stack:** HTML5, CSS, vanilla JavaScript, inline SVG, PowerShell validation, headless Microsoft Edge

---

### Task 1: Static mockup contract

**Files:**
- Create: `design-samples/portfolio-workbook-dashboard.test.ps1`
- Test: `design-samples/portfolio-workbook-dashboard.test.ps1`

- [ ] **Step 1: Write the failing validation script**

Create a script that loads `portfolio-workbook-dashboard.html`, fails when it is absent, and asserts the document contains the overview metrics, two allocation charts, portfolio-history chart, mutual-fund/equity/fixed-asset details, Excel upload preview, approved workbook-sheet names, and no credential/account fields.

- [ ] **Step 2: Run the validator and confirm the expected failure**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File design-samples/portfolio-workbook-dashboard.test.ps1
```

Expected: non-zero exit because `design-samples/portfolio-workbook-dashboard.html` does not exist.

### Task 2: Standalone dashboard page

**Files:**
- Create: `design-samples/portfolio-workbook-dashboard.html`
- Test: `design-samples/portfolio-workbook-dashboard.test.ps1`

- [ ] **Step 1: Build the semantic page structure**

Add a header, four summary cards, asset-allocation and mutual-fund-allocation chart cards, historical principal-versus-market-value chart, detail navigation, three portfolio detail sections, and upload-preview section.

- [ ] **Step 2: Add self-contained visualization and styling**

Use inline SVG for accessible pie/donut charts and the history line chart. Use only local CSS with responsive grids, readable legends, Indian currency formatting in displayed sample values, table overflow handling, and colors consistent with the existing dashboard.

- [ ] **Step 3: Add local-only interactions**

Implement detail-tab switching, chart legend emphasis, and an `.xlsx` file chooser that displays a simulated preview listing recognized sheets, excluded sheets, changed records, reconciliation status, and confirmation behavior. Do not upload, read, or persist the selected file.

- [ ] **Step 4: Run the static validator**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File design-samples/portfolio-workbook-dashboard.test.ps1
```

Expected: `PASS: portfolio workbook dashboard mockup contract`.

### Task 3: Browser rendering verification

**Files:**
- Verify: `design-samples/portfolio-workbook-dashboard.html`

- [ ] **Step 1: Render the page in headless Edge**

Open the absolute local HTML path at a desktop viewport and capture a full-page screenshot.

- [ ] **Step 2: Inspect layout and interactions**

Confirm that both pie charts render with legends, all dashboard sections are legible, tables do not overlap, the history chart spans its container, tabs switch visible panels, and selecting an `.xlsx` filename reveals the preview state.

- [ ] **Step 3: Re-run privacy and content validation**

Run the static validator again and verify the rendered DOM contains no password, login, folio, account-number, or source-URL values.

- [ ] **Step 4: Commit only mockup artifacts**

```powershell
git add design-samples/portfolio-workbook-dashboard.html design-samples/portfolio-workbook-dashboard.test.ps1
git commit -m "design: add portfolio workbook dashboard mockup"
```
