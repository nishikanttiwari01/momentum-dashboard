# Wealth Operating System Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the safe workbook-import, normalized snapshot, FX, consolidated-header, tab-shell, and visible-sort-indicator foundation required by the approved wealth operating system.

**Architecture:** Add normalized portfolio tables to the existing SQLite/Alembic store, parse supported workbook sheets into an in-memory preview, and persist the preview atomically only after explicit confirmation. Expose a focused FastAPI import/summary contract and adapt the existing React Portfolio page into a tabbed shell while keeping current mutual-fund and QQQ behavior mounted under Investments.

**Tech Stack:** Python 3, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, openpyxl, pytest, React 18, TypeScript, MUI 6, TanStack Query, Axios, Vitest.

---

## Master delivery roadmap

This approved product is too broad for one safe implementation plan. Deliver it as independently testable plans in this order:

1. **Foundation — this plan:** normalized storage, workbook preview/import, immutable snapshots, FX records, consolidated summary, Portfolio tabs, and visible sorting affordance.
2. **Overview:** balanced layout B, wealth history, current/target allocation, market exposure, goal progress, and snapshot deltas.
3. **Annual Review:** Jan–Dec reconciliation, investment XIRR, benchmarks, attribution, and rule-based insights.
4. **Properties & Rent:** dated valuations/overrides, rent/expense ledger, occupancy, and rental yields.
5. **Goals:** primary and secondary goals plus conservative/expected/optimistic projections.
6. **Refinement:** responsive polish, accessibility, performance, and complete browser regression coverage.

Each later plan must use the persisted entities and API contracts introduced here instead of reparsing Excel independently.

## Foundation file map

### Backend files to create

- `backend/app/schemas/wealth_portfolio.py` — request/response types shared by import and summary endpoints.
- `backend/app/services/wealth_workbook.py` — safe workbook recognition, extraction, issue reporting, and deterministic source IDs.
- `backend/app/services/wealth_import_service.py` — preview token handling and atomic persistence orchestration.
- `backend/app/services/wealth_fx_service.py` — current/historical USD/INR fetch with cached fallback metadata.
- `backend/app/services/wealth_summary_service.py` — latest-snapshot consolidated market-value calculation.
- `backend/app/api/v1/wealth_portfolio.py` — preview, commit, latest snapshot, and summary endpoints.
- `backend/alembic/versions/20260714_0007_wealth_portfolio_foundation.py` — normalized foundation tables.
- `backend/tests/services/test_wealth_workbook.py` — parser, ignored-sheet, duplicate, and issue tests.
- `backend/tests/services/test_wealth_import_service.py` — idempotency and atomic rollback tests.
- `backend/tests/services/test_wealth_fx_service.py` — live, historical, and stale-cache behavior.
- `backend/tests/api/test_wealth_portfolio_api.py` — multipart preview/commit/summary contract.
- `backend/tests/fixtures/wealth_workbook_factory.py` — small generated `.xlsx` fixtures without private workbook data.

### Backend files to modify

- `backend/requirements.txt` — add the pinned workbook reader.
- `backend/app/repos/models.py` — declare normalized ORM entities.
- `backend/app/main.py` — register the new router.
- `backend/tests/test_migrations.py` — assert the new schema upgrades cleanly.

### Frontend files to create

- `frontend/src/features/portfolio/wealthTypes.ts` — explicit API view models.
- `frontend/src/features/portfolio/wealthApi.ts` — preview, commit, and summary calls.
- `frontend/src/features/portfolio/PortfolioHub.tsx` — tab navigation and persistent summary header.
- `frontend/src/features/portfolio/PortfolioSummaryHeader.tsx` — consolidated KPIs and refresh/FX metadata.
- `frontend/src/features/portfolio/PortfolioDataImport.tsx` — upload, preview, issue, and commit workflow.
- `frontend/src/features/portfolio/PortfolioHub.test.tsx` — tab and existing-content preservation tests.
- `frontend/src/features/portfolio/PortfolioDataImport.test.tsx` — preview/commit/error-state tests.
- `frontend/src/features/portfolio/PortfolioSummaryHeader.test.tsx` — money/FX/stale rendering tests.

### Frontend files to modify

- `frontend/src/pages/Portfolio.tsx` — make the existing page content the Investments panel and mount the hub.
- `frontend/src/features/portfolio/PortfolioWorkbookPreview.tsx` — replace preview-only behavior with the real import component or remove after callers migrate.
- `frontend/src/features/portfolio/PortfolioWorkbookPreview.test.tsx` — replace preview-only assertions.
- `frontend/src/features/portfolio/FundTableSortingStyle.test.ts` — require neutral arrows for inactive sortable columns.

## API contract fixed by this plan

- `POST /api/v1/wealth-portfolio/imports/preview` accepts multipart field `workbook` and returns `preview_token`, recognized/ignored sheets, counts, issues, and source fingerprint.
- `POST /api/v1/wealth-portfolio/imports/{preview_token}/commit` atomically creates one immutable snapshot. Recommitting the same fingerprint returns the existing snapshot with `created=false`.
- `GET /api/v1/wealth-portfolio/snapshots/latest` returns the latest snapshot metadata.
- `GET /api/v1/wealth-portfolio/summary` returns consolidated INR market value, invested capital, investment XIRR when available, market split, FX metadata, and data-health status.

Preview tokens are server-side, expire after 30 minutes, and never expose workbook bytes or ignored-sheet values to the client.

### Task 1: Add workbook dependency and migration

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/repos/models.py`
- Create: `backend/alembic/versions/20260714_0007_wealth_portfolio_foundation.py`
- Modify: `backend/tests/test_migrations.py`

- [ ] **Step 1: Write the migration assertions**

Add to `backend/tests/test_migrations.py`:

```python
def test_wealth_foundation_tables_exist(upgraded_connection):
    names = {
        row[0]
        for row in upgraded_connection.exec_driver_sql(
            "select name from sqlite_master where type='table'"
        )
    }
    assert {
        "portfolio_imports", "portfolio_snapshots", "portfolio_assets",
        "portfolio_transactions", "portfolio_valuations", "portfolio_fx_rates",
    } <= names
```

- [ ] **Step 2: Run the migration test and verify failure**

Run: `cd backend; pytest tests/test_migrations.py::test_wealth_foundation_tables_exist -v`

Expected: FAIL because the six tables do not exist.

- [ ] **Step 3: Add the dependency and ORM models**

Append `openpyxl==3.1.5` to `backend/requirements.txt`. In `backend/app/repos/models.py`, add focused models matching these fields:

```python
class PortfolioImport(Base):
    __tablename__ = "portfolio_imports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    filename: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), index=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    issue_counts: Mapped[dict] = mapped_column(JSON, default=dict)

class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    import_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    as_of: Mapped[date] = mapped_column(Date, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

class PortfolioAsset(Base):
    __tablename__ = "portfolio_assets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(String(36), index=True)
    source_key: Mapped[str] = mapped_column(String(64))
    asset_type: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(255))
    market: Mapped[str] = mapped_column(String(16), index=True)
    currency: Mapped[str] = mapped_column(String(3))
    invested_amount: Mapped[Optional[float]] = mapped_column(Float)
    market_value: Mapped[Optional[float]] = mapped_column(Float)
    source_ref: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("snapshot_id", "source_key"),)

class PortfolioTransaction(Base):
    __tablename__ = "portfolio_transactions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(String(36), index=True)
    source_key: Mapped[str] = mapped_column(String(64))
    asset_id: Mapped[str] = mapped_column(String(64), index=True)
    occurred_on: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(16))
    amount: Mapped[float] = mapped_column(Float)
    units: Mapped[Optional[float]] = mapped_column(Float)
    unit_price: Mapped[Optional[float]] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3))
    source_ref: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("snapshot_id", "source_key"),)

class PortfolioValuation(Base):
    __tablename__ = "portfolio_valuations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(String(36), index=True)
    source_key: Mapped[str] = mapped_column(String(64))
    asset_id: Mapped[str] = mapped_column(String(64), index=True)
    valued_on: Mapped[date] = mapped_column(Date, index=True)
    market_value: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3))
    source_ref: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("snapshot_id", "source_key"),)

class PortfolioFxRate(Base):
    __tablename__ = "portfolio_fx_rates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    base_currency: Mapped[str] = mapped_column(String(3))
    quote_currency: Mapped[str] = mapped_column(String(3))
    effective_on: Mapped[date] = mapped_column(Date)
    rate: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(DateTime)
    __table_args__ = (UniqueConstraint("base_currency", "quote_currency", "effective_on"),)
```

Create the Alembic revision with equivalent columns, indexes, uniqueness constraints, and a downgrade that drops only these six tables in reverse dependency order.

- [ ] **Step 4: Run migration tests**

Run: `cd backend; pytest tests/test_migrations.py -v`

Expected: PASS, including upgrade from baseline and the new table assertion.

- [ ] **Step 5: Commit**

```bash
git add backend/requirements.txt backend/app/repos/models.py backend/alembic/versions/20260714_0007_wealth_portfolio_foundation.py backend/tests/test_migrations.py
git commit -m "feat: add wealth portfolio foundation schema"
```

### Task 2: Define import and summary schemas

**Files:**
- Create: `backend/app/schemas/wealth_portfolio.py`
- Create: `backend/tests/services/test_wealth_schemas.py`

- [ ] **Step 1: Write schema validation tests**

```python
from pydantic import ValidationError
from app.schemas.wealth_portfolio import ImportIssue, ImportPreview

def test_import_issue_rejects_sensitive_details():
    try:
        ImportIssue(severity="warning", code="x", message="x", sheet="MF discont.", row=1)
    except ValidationError:
        return
    raise AssertionError("ignored sheet must not appear in client issue details")

def test_preview_separates_recognized_and_ignored_sheets():
    preview = ImportPreview(
        preview_token="token", source_sha256="a" * 64,
        recognized_sheets=["FUNDS"], ignored_sheets=["MF discont."],
        counts={"assets": 1, "transactions": 0, "valuations": 1}, issues=[],
    )
    assert preview.blocking_error_count == 0
```

- [ ] **Step 2: Run and verify failure**

Run: `cd backend; pytest tests/services/test_wealth_schemas.py -v`

Expected: FAIL because the schema module is absent.

- [ ] **Step 3: Implement explicit Pydantic contracts**

Create enums/literals for severity and health, then define `ImportIssue`, `ImportPreview`, `ImportCommitResult`, `SnapshotSummary`, `FxMetadata`, `MarketExposure`, and `WealthSummary`. `ImportIssue` must reject `sheet` values in `{"MF discont.", "Property Cal.", "REMIT", "STOCKS RECMDN"}` so ignored-sheet row details cannot leak.

```python
class ImportIssue(BaseModel):
    severity: Literal["warning", "error"]
    code: str
    message: str
    sheet: str | None = None
    row: int | None = Field(None, ge=1)

    @model_validator(mode="after")
    def protect_ignored_sheets(self):
        if self.sheet in IGNORED_SHEETS:
            raise ValueError("ignored sheet details cannot be exposed")
        return self

class ImportPreview(BaseModel):
    preview_token: str
    source_sha256: str
    recognized_sheets: list[str]
    ignored_sheets: list[str]
    counts: dict[str, int]
    issues: list[ImportIssue]

    @computed_field
    @property
    def blocking_error_count(self) -> int:
        return sum(issue.severity == "error" for issue in self.issues)
```

- [ ] **Step 4: Run schema tests**

Run: `cd backend; pytest tests/services/test_wealth_schemas.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/wealth_portfolio.py backend/tests/services/test_wealth_schemas.py
git commit -m "feat: define wealth import contracts"
```

### Task 3: Parse supported workbook data safely

**Files:**
- Create: `backend/tests/fixtures/wealth_workbook_factory.py`
- Create: `backend/tests/services/test_wealth_workbook.py`
- Create: `backend/app/services/wealth_workbook.py`

- [ ] **Step 1: Generate a minimal workbook fixture in the test**

The factory must create only synthetic values and these sheets: `BALANCE SHEET`, `CURRENT ASSET`, `FUNDS`, `Funds XIRR`, `Final XIRR`, `EQUITY`, `FIXED ASSET`, `GOALS`, `MNTHLY INCOM PLAN`, `Gera office roi`, plus ignored sheets containing sentinel text.

```python
def make_workbook_bytes() -> bytes:
    wb = Workbook()
    funds = wb.active
    funds.title = "FUNDS"
    funds.append(["Fund", "Principal", "Market Value", "Category"])
    funds.append(["Example Mid Cap", 400000, 520000, "Mid cap"])
    xirr = wb.create_sheet("Funds XIRR")
    xirr.append(["Fund", "Date", "Amount", "Units", "NAV"])
    xirr.append(["Example Mid Cap", date(2025, 3, 6), 400000, 4025.481297, 99.367])
    ignored = wb.create_sheet("MF discont.")
    ignored.append(["DO_NOT_EXPOSE"])
    stream = BytesIO(); wb.save(stream); return stream.getvalue()
```

- [ ] **Step 2: Write parser behavior tests**

```python
def test_parser_extracts_assets_transactions_and_valuations():
    result = parse_workbook(make_workbook_bytes(), "investment.xlsx")
    assert result.counts == {"assets": 1, "transactions": 1, "valuations": 1}
    assert result.assets[0].name == "Example Mid Cap"

def test_parser_reports_ignored_sheet_without_reading_cells():
    result = parse_workbook(make_workbook_bytes(), "investment.xlsx")
    assert "MF discont." in result.ignored_sheets
    assert "DO_NOT_EXPOSE" not in result.model_dump_json()

def test_parser_assigns_same_source_id_on_repeat_parse():
    payload = make_workbook_bytes()
    assert parse_workbook(payload, "a.xlsx").transactions[0].id == parse_workbook(payload, "b.xlsx").transactions[0].id
```

- [ ] **Step 3: Run and verify failure**

Run: `cd backend; pytest tests/services/test_wealth_workbook.py -v`

Expected: FAIL because `parse_workbook` does not exist.

- [ ] **Step 4: Implement the parser**

Use `openpyxl.load_workbook(BytesIO(payload), read_only=True, data_only=True)`. Check sheet names before accessing worksheets. Normalize headings with whitespace/case folding. Build deterministic `source_key` values with SHA-256 over normalized asset name, date, amount, units, and unit price. Persisted row IDs are UUIDs; uniqueness is enforced by `(snapshot_id, source_key)` so the same transaction may safely appear in successive immutable snapshots without duplicating inside one snapshot.

```python
IGNORED_SHEETS = frozenset({"MF discont.", "Property Cal.", "REMIT", "STOCKS RECMDN"})
SUPPORTED_SHEETS = frozenset({
    "BALANCE SHEET", "CURRENT ASSET", "FUNDS", "Funds XIRR", "Final XIRR",
    "EQUITY", "FIXED ASSET", "GOALS", "MNTHLY INCOM PLAN", "Gera office roi",
})

def parse_workbook(payload: bytes, filename: str) -> ParsedWorkbook:
    source_sha256 = sha256(payload).hexdigest()
    workbook = load_workbook(BytesIO(payload), read_only=True, data_only=True)
    recognized = [name for name in workbook.sheetnames if name in SUPPORTED_SHEETS]
    ignored = [name for name in workbook.sheetnames if name in IGNORED_SHEETS]
    assets = _parse_funds(workbook["FUNDS"]) if "FUNDS" in recognized else []
    transactions = _parse_fund_xirr(workbook["Funds XIRR"], assets) if "Funds XIRR" in recognized else []
    valuations = _latest_asset_valuations(assets)
    return ParsedWorkbook(
        source_sha256=source_sha256, filename=filename,
        recognized_sheets=recognized, ignored_sheets=ignored,
        assets=assets, transactions=transactions, valuations=valuations,
        issues=_validate_records(assets, transactions, valuations),
    )
```

The first implementation extracts fund assets and fund cash flows completely, recognizes the other approved sheets, and emits a non-blocking `sheet_parser_pending` warning for recognized sheets not yet normalized. It must not invent records from ambiguous layouts.

- [ ] **Step 5: Run parser tests**

Run: `cd backend; pytest tests/services/test_wealth_workbook.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/fixtures/wealth_workbook_factory.py backend/tests/services/test_wealth_workbook.py backend/app/services/wealth_workbook.py
git commit -m "feat: parse portfolio workbook safely"
```

### Task 4: Add preview storage and atomic import

**Files:**
- Create: `backend/app/services/wealth_import_service.py`
- Create: `backend/tests/services/test_wealth_import_service.py`

- [ ] **Step 1: Write idempotency and rollback tests**

```python
def test_same_fingerprint_returns_existing_snapshot(session, workbook_bytes):
    preview = service.preview(workbook_bytes, "investment.xlsx")
    first = service.commit(session, preview.preview_token)
    second_preview = service.preview(workbook_bytes, "renamed.xlsx")
    second = service.commit(session, second_preview.preview_token)
    assert first.snapshot_id == second.snapshot_id
    assert second.created is False

def test_blocking_issue_writes_nothing(session, invalid_workbook_bytes):
    preview = service.preview(invalid_workbook_bytes, "bad.xlsx")
    with pytest.raises(ImportBlocked):
        service.commit(session, preview.preview_token)
    assert session.query(PortfolioSnapshot).count() == 0
```

- [ ] **Step 2: Run and verify failure**

Run: `cd backend; pytest tests/services/test_wealth_import_service.py -v`

Expected: FAIL because the service does not exist.

- [ ] **Step 3: Implement expiring previews and one transaction commit**

Use an in-process `PreviewStore` guarded by `threading.Lock`; entries contain parsed records and expire after 30 minutes. `commit()` checks blocking errors and existing fingerprint before entering `with session.begin():`.

```python
def commit(self, session: Session, token: str) -> ImportCommitResult:
    parsed = self.store.pop_valid(token)
    if any(issue.severity == "error" for issue in parsed.issues):
        raise ImportBlocked("preview contains blocking errors")
    with session.begin():
        existing = session.scalar(select(PortfolioImport).where(PortfolioImport.source_sha256 == parsed.source_sha256))
        if existing:
            snapshot = session.scalar(select(PortfolioSnapshot).where(PortfolioSnapshot.import_id == existing.id))
            return ImportCommitResult(snapshot_id=snapshot.id, created=False)
        import_row, snapshot = _insert_import_and_snapshot(session, parsed)
        _insert_assets(session, snapshot.id, parsed.assets)
        _insert_transactions(session, snapshot.id, parsed.transactions)
        _insert_valuations(session, snapshot.id, parsed.valuations)
    return ImportCommitResult(snapshot_id=snapshot.id, created=True)
```

Set the snapshot `as_of` date to the latest effective date found among parsed valuations and transactions. If the workbook contains neither, use the server's current local date and add a `snapshot_date_inferred` warning to the preview.

- [ ] **Step 4: Run service tests**

Run: `cd backend; pytest tests/services/test_wealth_import_service.py -v`

Expected: PASS, including forced insert failure leaving all six portfolio tables unchanged.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/wealth_import_service.py backend/tests/services/test_wealth_import_service.py
git commit -m "feat: persist immutable portfolio snapshots"
```

### Task 5: Add FX service and consolidated summary

**Files:**
- Create: `backend/app/services/wealth_fx_service.py`
- Create: `backend/app/services/wealth_summary_service.py`
- Create: `backend/tests/services/test_wealth_fx_service.py`
- Create: `backend/tests/services/test_wealth_summary_service.py`

- [ ] **Step 1: Write FX fallback tests with `respx`**

```python
def test_current_rate_is_cached(session, respx_mock):
    respx_mock.get("https://api.frankfurter.app/latest?from=USD&to=INR").mock(
        return_value=httpx.Response(200, json={"date": "2026-07-14", "rates": {"INR": 86.25}})
    )
    result = get_usd_inr(session, date(2026, 7, 14))
    assert result.rate == 86.25 and result.is_fallback is False

def test_network_failure_uses_latest_cached_rate(session):
    seed_rate(session, effective_on=date(2026, 7, 13), rate=86.1)
    result = get_usd_inr(session, date(2026, 7, 14), client=FailingClient())
    assert result.rate == 86.1 and result.is_fallback is True
```

- [ ] **Step 2: Write consolidated summary test**

```python
def test_summary_converts_usd_and_includes_property(session, snapshot):
    add_asset(session, snapshot, "Indian MF", "mutual_fund", "IN", "INR", 400000, 520000)
    add_asset(session, snapshot, "QQQ", "etf", "US", "USD", 1000, 1200)
    add_asset(session, snapshot, "Office", "property", "IN", "INR", 5000000, 6500000)
    summary = build_summary(session, fx=FxResult(rate=86.25, effective_on=date(2026, 7, 14), is_fallback=False))
    assert summary.net_worth_market_value_inr == 520000 + 1200 * 86.25 + 6500000
    assert summary.invested_capital_inr == 400000 + 1000 * 86.25 + 5000000
```

- [ ] **Step 3: Run and verify failure**

Run: `cd backend; pytest tests/services/test_wealth_fx_service.py tests/services/test_wealth_summary_service.py -v`

Expected: FAIL because the services are absent.

- [ ] **Step 4: Implement FX cache and summary**

Use Frankfurter's date endpoint (`/{YYYY-MM-DD}?from=USD&to=INR`) for historical values and latest endpoint for current values. Inject the HTTP client in tests. Summary uses the latest snapshot, converts each asset, returns market exposure percentages, and reports `investment_xirr_pct=None` until the Annual Review plan supplies a complete cash-flow engine.

```python
def convert_to_inr(amount: float | None, currency: str, fx: FxResult) -> float | None:
    if amount is None:
        return None
    if currency == "INR":
        return amount
    if currency == "USD":
        return amount * fx.rate
    raise UnsupportedCurrency(currency)
```

- [ ] **Step 5: Run service tests**

Run: `cd backend; pytest tests/services/test_wealth_fx_service.py tests/services/test_wealth_summary_service.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/wealth_fx_service.py backend/app/services/wealth_summary_service.py backend/tests/services/test_wealth_fx_service.py backend/tests/services/test_wealth_summary_service.py
git commit -m "feat: summarize consolidated multi-currency wealth"
```

### Task 6: Expose import and summary API

**Files:**
- Create: `backend/app/api/v1/wealth_portfolio.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/api/test_wealth_portfolio_api.py`

- [ ] **Step 1: Write API tests**

```python
def test_preview_then_commit(client, workbook_bytes):
    preview = client.post(
        "/api/v1/wealth-portfolio/imports/preview",
        files={"workbook": ("investment.xlsx", workbook_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["recognized_sheets"]
    committed = client.post(f"/api/v1/wealth-portfolio/imports/{body['preview_token']}/commit")
    assert committed.status_code == 201

def test_rejects_wrong_extension(client):
    response = client.post("/api/v1/wealth-portfolio/imports/preview", files={"workbook": ("notes.csv", b"x", "text/csv")})
    assert response.status_code == 422
```

- [ ] **Step 2: Run and verify failure**

Run: `cd backend; pytest tests/api/test_wealth_portfolio_api.py -v`

Expected: FAIL with 404.

- [ ] **Step 3: Implement and register the router**

Limit uploads to 20 MiB, require `.xlsx`, pass only bytes and basename to the parser, map expired tokens to 404, blocking previews to 409, and successful new commits to 201.

```python
router = APIRouter(prefix="/wealth-portfolio", tags=["Wealth Portfolio"])

@router.post("/imports/preview", response_model=ImportPreview)
async def preview_import(workbook: UploadFile = File(...)):
    if not workbook.filename or not workbook.filename.lower().endswith(".xlsx"):
        raise HTTPException(422, "Only .xlsx workbooks are supported")
    payload = await workbook.read(MAX_WORKBOOK_BYTES + 1)
    if len(payload) > MAX_WORKBOOK_BYTES:
        raise HTTPException(413, "Workbook exceeds 20 MiB")
    return import_service.preview(payload, Path(workbook.filename).name)
```

Import `wealth_portfolio` in `backend/app/main.py` and register `app.include_router(wealth_portfolio.router, prefix=prefix)` beside the existing portfolio routers.

- [ ] **Step 4: Run API and route tests**

Run: `cd backend; pytest tests/api/test_wealth_portfolio_api.py tests/test_routes_json.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/wealth_portfolio.py backend/app/main.py backend/tests/api/test_wealth_portfolio_api.py
git commit -m "feat: expose wealth workbook import API"
```

### Task 7: Build frontend API client and import workflow

**Files:**
- Create: `frontend/src/features/portfolio/wealthTypes.ts`
- Create: `frontend/src/features/portfolio/wealthApi.ts`
- Create: `frontend/src/features/portfolio/PortfolioDataImport.tsx`
- Create: `frontend/src/features/portfolio/PortfolioDataImport.test.tsx`
- Modify: `frontend/src/features/portfolio/PortfolioWorkbookPreview.tsx`
- Modify: `frontend/src/features/portfolio/PortfolioWorkbookPreview.test.tsx`

- [ ] **Step 1: Write the interaction test**

Use MSW to return a preview containing one warning and zero blocking errors, then assert Commit becomes enabled only after preview succeeds.

```tsx
it('previews an xlsx and commits the immutable snapshot', async () => {
  render(<QueryClientProvider client={client}><PortfolioDataImport /></QueryClientProvider>);
  const file = new File(['workbook'], 'investment.xlsx', { type: XLSX_MIME });
  await userEvent.upload(screen.getByLabelText(/choose.*workbook/i), file);
  expect(await screen.findByText('1 asset')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: /import snapshot/i }));
  expect(await screen.findByText(/snapshot imported/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run and verify failure**

Run: `cd frontend; npm test -- --run src/features/portfolio/PortfolioDataImport.test.tsx`

Expected: FAIL because the component is absent.

- [ ] **Step 3: Implement explicit types, calls, and UI states**

`wealthApi.ts` must send `FormData` without manually setting the multipart boundary and return typed payloads.

```ts
export async function previewWorkbook(file: File): Promise<ImportPreview> {
  const form = new FormData();
  form.append('workbook', file);
  return (await axios.post('/api/v1/wealth-portfolio/imports/preview', form)).data;
}

export async function commitWorkbook(token: string): Promise<ImportCommitResult> {
  return (await axios.post(`/api/v1/wealth-portfolio/imports/${token}/commit`)).data;
}
```

`PortfolioDataImport` renders idle, uploading, preview-ready, blocking-error, committing, success, and request-error states. It lists recognized/ignored sheet names and counts, but never workbook cell content from ignored sheets. Disable Import when `blocking_error_count > 0`.

Replace `PortfolioWorkbookPreview` with a compatibility export:

```tsx
export { default } from './PortfolioDataImport';
```

- [ ] **Step 4: Run component tests**

Run: `cd frontend; npm test -- --run src/features/portfolio/PortfolioDataImport.test.tsx src/features/portfolio/PortfolioWorkbookPreview.test.tsx`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/portfolio/wealthTypes.ts frontend/src/features/portfolio/wealthApi.ts frontend/src/features/portfolio/PortfolioDataImport.tsx frontend/src/features/portfolio/PortfolioDataImport.test.tsx frontend/src/features/portfolio/PortfolioWorkbookPreview.tsx frontend/src/features/portfolio/PortfolioWorkbookPreview.test.tsx
git commit -m "feat: add portfolio workbook import workflow"
```

### Task 8: Add Portfolio hub and persistent summary

**Files:**
- Create: `frontend/src/features/portfolio/PortfolioSummaryHeader.tsx`
- Create: `frontend/src/features/portfolio/PortfolioSummaryHeader.test.tsx`
- Create: `frontend/src/features/portfolio/PortfolioHub.tsx`
- Create: `frontend/src/features/portfolio/PortfolioHub.test.tsx`
- Modify: `frontend/src/pages/Portfolio.tsx`

- [ ] **Step 1: Extract current Portfolio content without changing behavior**

Rename the current default component to `PortfolioInvestmentsPanel` and keep its queries, fund table, NAV charts, transaction dialogs, allocation, and US section unchanged. Export it as a named component for the hub.

- [ ] **Step 2: Write hub preservation and navigation tests**

```tsx
it('keeps existing fund and US content under Investments', async () => {
  render(<PortfolioHub investments={<div>Mutual funds and QQQ</div>} />);
  await userEvent.click(screen.getByRole('tab', { name: 'Investments' }));
  expect(screen.getByText('Mutual funds and QQQ')).toBeVisible();
});

it('opens Data Import without unmounting the portfolio route', async () => {
  render(<PortfolioHub investments={<div>Investments</div>} />);
  await userEvent.click(screen.getByRole('tab', { name: 'Data Import' }));
  expect(screen.getByLabelText(/choose.*workbook/i)).toBeVisible();
});
```

- [ ] **Step 3: Run and verify failure**

Run: `cd frontend; npm test -- --run src/features/portfolio/PortfolioHub.test.tsx src/features/portfolio/PortfolioSummaryHeader.test.tsx`

Expected: FAIL because the hub/header are absent.

- [ ] **Step 4: Implement the tab shell and summary header**

Tabs are `Overview`, `Annual Review`, `Investments`, `Properties & Rent`, `Goals`, and `Data Import`. Foundation defaults to Investments so current users land on working functionality. Non-foundation tabs show an honest “Available in the next portfolio phase” empty state, not fabricated analytics.

```tsx
const TAB_LABELS = ['Overview', 'Annual Review', 'Investments', 'Properties & Rent', 'Goals', 'Data Import'] as const;

export default function PortfolioHub({ investments }: { investments: React.ReactNode }) {
  const [tab, setTab] = React.useState(2);
  return <>
    <PortfolioSummaryHeader />
    <Tabs value={tab} onChange={(_, value) => setTab(value)} variant="scrollable">
      {TAB_LABELS.map(label => <Tab key={label} label={label} />)}
    </Tabs>
    {tab === 2 ? investments : tab === 5 ? <PortfolioDataImport /> : <PortfolioPhaseEmptyState label={TAB_LABELS[tab]} />}
  </>;
}
```

`PortfolioSummaryHeader` fetches `/api/v1/wealth-portfolio/summary`; before the first snapshot it displays “Import investment.xlsx to build consolidated wealth” while the existing Investments panel still works.

- [ ] **Step 5: Run hub tests and full frontend build**

Run: `cd frontend; npm test -- --run src/features/portfolio/PortfolioHub.test.tsx src/features/portfolio/PortfolioSummaryHeader.test.tsx src/pages/PortfolioStyle.test.ts`

Expected: PASS.

Run: `cd frontend; npm run build`

Expected: TypeScript and Vite build complete successfully.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/portfolio/PortfolioSummaryHeader.tsx frontend/src/features/portfolio/PortfolioSummaryHeader.test.tsx frontend/src/features/portfolio/PortfolioHub.tsx frontend/src/features/portfolio/PortfolioHub.test.tsx frontend/src/pages/Portfolio.tsx
git commit -m "feat: add tabbed wealth portfolio hub"
```

### Task 9: Make sortable headers visibly discoverable

**Files:**
- Modify: `frontend/src/pages/Portfolio.tsx`
- Modify: `frontend/src/features/portfolio/FundTableSortingStyle.test.ts`

- [ ] **Step 1: Add the failing style assertion**

Assert inactive `TableSortLabel` controls retain `hideSortIcon={false}` and use a neutral icon opacity, while active labels use the accent color.

```ts
expect(source).toContain('hideSortIcon={false}');
expect(source).toContain("'& .MuiTableSortLabel-icon': { opacity: 0.35 }");
expect(source).toContain("'&.Mui-active .MuiTableSortLabel-icon': { opacity: 1");
```

- [ ] **Step 2: Run and verify failure**

Run: `cd frontend; npm test -- --run src/features/portfolio/FundTableSortingStyle.test.ts`

Expected: FAIL because inactive sort icons are hidden or not styled.

- [ ] **Step 3: Apply the discoverable sort styling**

For every sortable mutual-fund header, set:

```tsx
<TableSortLabel
  active={sortKey === column.key}
  direction={sortKey === column.key ? sortDirection : 'asc'}
  hideSortIcon={false}
  sx={{
    '& .MuiTableSortLabel-icon': { opacity: 0.35 },
    '&.Mui-active .MuiTableSortLabel-icon': { opacity: 1, color: 'primary.main' },
  }}
>
```

- [ ] **Step 4: Run sorting and build verification**

Run: `cd frontend; npm test -- --run src/features/portfolio/FundTableSortingStyle.test.ts src/features/portfolio/fundTableSort.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Portfolio.tsx frontend/src/features/portfolio/FundTableSortingStyle.test.ts
git commit -m "fix: show portfolio sorting affordances"
```

### Task 10: End-to-end foundation verification

**Files:**
- Create: `backend/tests/e2e/test_wealth_import_to_summary.py`
- Modify: `docs/data-storage.md`

- [ ] **Step 1: Add an import-to-summary test**

The test uploads the synthetic workbook, commits it, stubs USD/INR, fetches summary, and asserts the snapshot ID and INR totals reconcile with stored assets.

```python
def test_workbook_import_produces_latest_summary(client, workbook_bytes, stub_fx):
    preview = client.post("/api/v1/wealth-portfolio/imports/preview", files={"workbook": ("investment.xlsx", workbook_bytes, XLSX_MIME)}).json()
    committed = client.post(f"/api/v1/wealth-portfolio/imports/{preview['preview_token']}/commit").json()
    summary = client.get("/api/v1/wealth-portfolio/summary").json()
    assert summary["snapshot_id"] == committed["snapshot_id"]
    assert summary["net_worth_market_value_inr"] > 0
    assert summary["data_health"] in {"fresh", "warning"}
```

- [ ] **Step 2: Run all focused backend tests**

Run: `cd backend; pytest tests/services/test_wealth_schemas.py tests/services/test_wealth_workbook.py tests/services/test_wealth_import_service.py tests/services/test_wealth_fx_service.py tests/services/test_wealth_summary_service.py tests/api/test_wealth_portfolio_api.py tests/e2e/test_wealth_import_to_summary.py tests/test_migrations.py -v`

Expected: PASS with no workbook sentinel text in captured logs.

- [ ] **Step 3: Run all focused frontend tests and build**

Run: `cd frontend; npm test -- --run src/features/portfolio src/pages/PortfolioStyle.test.ts`

Expected: PASS.

Run: `cd frontend; npm run build`

Expected: PASS.

- [ ] **Step 4: Perform browser verification with a real rendered page**

Start the backend and frontend using the repository's documented commands. Open the Portfolio route at desktop width and verify:

1. all six tabs are reachable by keyboard;
2. Investments retains Indian mutual funds, QQQ, transaction entry, charts, and tables;
3. neutral sort arrows are visible before sorting and active arrows change state;
4. Data Import previews `investment.xlsx` without showing ignored-sheet cells;
5. canceling preview changes no totals;
6. committing creates a new dated snapshot and refreshes the header;
7. repeating the same workbook reports the existing snapshot instead of duplicating data;
8. the header displays applied USD/INR date and fallback state;
9. at tablet width the tabs scroll and the page has no whole-page horizontal overflow.

Capture screenshots of Investments, Data Import preview, and the post-import header in the task evidence. Do not claim completion from unit tests alone.

- [ ] **Step 5: Document storage and privacy boundaries**

Update `docs/data-storage.md` with table purposes, snapshot immutability, 30-minute in-memory preview expiry, deterministic IDs, ignored sheets, FX provenance, and backup implications.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/e2e/test_wealth_import_to_summary.py docs/data-storage.md
git commit -m "test: verify wealth import foundation end to end"
```

## Foundation completion criteria

- A valid `.xlsx` can be previewed and committed from the Portfolio page.
- No failed or canceled preview changes persisted portfolio data.
- Re-importing identical bytes does not create duplicate snapshots or transactions.
- Ignored sheets are never opened, logged, persisted, or returned beyond their sheet names.
- The latest immutable snapshot produces a consolidated INR headline with explicit FX provenance.
- Existing Indian mutual-fund and QQQ features still work under Investments.
- All sortable mutual-fund headers show arrows before interaction.
- Focused backend/frontend tests, production build, migration test, and browser verification pass.
- Later Overview, Annual Review, Properties, and Goals work can build on the stored entities without parsing Excel again.
