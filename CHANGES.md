# Momentum Dashboard — Change Log (Analysis-Report Fix Pass)

Window: continuation of the Analysis_Report.md remediation.
Scope: code-only fixes inside the existing app, no LLM/context-layer work.

## Summary of edits

| # | Tier | Area | Files touched |
|---|------|------|---------------|
| 1 | A | Scheduler silent-failure + metric_getter contract | `backend/app/workers/scheduler.py` |
| 2 | B | Simulator realism (grid-search → walk-forward; honest metrics) | `backend/app/services/simulator_service.py` |
| 3 | B | Selection bottleneck (multi-pick per scan + per-run sector cap) | `backend/app/core/config.py`, `backend/app/services/selection_service.py`, `backend/app/services/screening_service.py`, `configs/default.yaml` |
| 4 | B | Exit ladder (T1 auto-arm breakeven, retrace-band semantic fix) | `backend/app/services/sell_engine.py`, `configs/default.yaml` |
| 5 | C | Alert dedupe → best-in-session upgrade | `backend/app/alerts/dedupe.py`, `backend/app/alerts/persist.py`, `backend/app/alerts/router.py` |
| 6 | C | Secrets out of alerts.yaml | `configs/alerts.yaml` |
| 7 | C | Fail-loud config validation at startup | `backend/app/core/config_validation.py` (new), `backend/app/main.py` |

All files compile cleanly (`python -m compileall app/`).

---

## 1. Scheduler silent-failure + metric_getter contract  (Tier A #2)

Previously, when parquet was empty or the alert handler threw, the scheduler ate the exception and moved on, so the 15-minute loop looked healthy while producing zero alerts. The `metric_getter` contract (`Callable[[str, str], Any]`) was also brittle: some call sites passed dicts, others passed row lookups, and silent `None`s flowed through without trace.

Fix: tightened the scheduler guard so parquet-empty and handler exceptions are logged at ERROR level with the scan context, and normalised the `metric_getter` factory so every call returns a typed-predictable value (or an explicit `None` with a log line). The scheduler now also increments a run-level failure counter, which the next scan uses as a health signal.

## 2. Simulator realism  (Tier B #4)

`simulator_service.py` contained three anti-patterns that together made the backtest a narrative-validation tool rather than an evidence source:

- `_build_sweep_variants` did a grid search over parameter ranges — an overfitting trap.
- `target_total_return_pct` allowed early-stop when a run "hit the number," biasing toward lucky paths.
- `prefer_profitable` ranked variant output by terminal PnL — classic sorted-by-luck bias.

Removed all three. The `sweep` flag is now repurposed as a **walk-forward** switch: contiguous, non-overlapping splits of the sim window; each split reports its own metrics; the aggregate summary reports stability of out-of-sample stats across splits. Parameters that used to drive the grid (`ranges`, `min_runs`, `seed`, `prefer_profitable`, `target_total_return_pct`) are now surfaced under `meta.ignored_sweep_keys` so callers see explicitly that they were not used.

New per-run summary fields: `sharpe_annualised`, `sortino_annualised`, `cagr_pct`, `profit_factor`, `expectancy_per_trade_pct`, `monthly_return_pct_by_month`, `positive_months`, `negative_months`, `slots_assumed`, plus a day-level equity curve feeding all of the above. Stats are pure-python (no scipy); drawdown is computed from the equity curve.

## 3. Selection bottleneck  (Tier B #5)

Original flow: `apply_selection_policy()` returned at most one pick per scan. A 5-slot book therefore needed five clean scans to fill — meaning a strong setup day routinely filled only 1–2 slots.

Added:
- `strategy.selection_policy.top_n_per_run` (default **2**)
- `strategy.selection_policy.max_per_sector_per_run` (default **1**) — prevents one hot sector crowding out diversification within a single scan.

New helper `apply_selection_policy_multi()` in `selection_service.py` returns a list up to `top_n_per_run`, honoring all existing gates (weekly quota, symbol cooldown, sector cooldown, max_open_positions) plus the new per-run sector cap. The existing single-pick function is preserved for back-compat; `screening_service.py` prefers multi and falls back to single, mirrors the first pick into the legacy `selection_result` slot, and wraps BUY_SELECTED dispatch in a for-loop so multiple picks each fire their own alert.

## 4. Exit ladder  (Tier B #6)

Two bugs compounded in `sell_engine.py`:

1. **`retrace_to_pct` semantic was inverted in practice.** The default `0.10` combined with `gain_pct=5` meant the breakeven trigger fired at *arm time* — any price ≥+5% is also ≤+10%, so the "protect profit on pullback" rule acted as an immediate exit. Default now `0.0` (true breakeven exit if price returns to entry). Added an `armed_on_this_bar` guard so the trigger can never fire on the same bar that armed it.
2. **T1 touch didn't arm the breakeven trail.** Positions that hit T1 then gave it all back continued to trade against the original stop. Added: when `t1_hit` is true and breakeven isn't yet active, auto-arm it and stamp `breakeven_armed_by="t1_touch"` in the note so the event is auditable.

Also: `breakeven.intraday_enabled` flipped from `false` → `true` in `default.yaml`. Most profitable-turned-losing trades give up the gain intraday; waiting for EOD to protect the profit defeats the purpose of the ladder.

## 5. Alert dedupe → best-in-session upgrade  (Tier C #8)

Previously, `router.route_event` hard-skipped any second event within the same `(rule_code, symbol, trading_date, mode, bucket_ord)` tuple. Consequence: the first weak signal of a bucket "locked in" the row, even if the same bucket later produced a much stronger read (e.g. score climbed 72 → 86 within a 15-minute window).

New flow:

- `dedupe.get_existing_event(...)` returns `(event_id, score_at_fire)` for the latest row in that slot (or `None`).
- `persist.update_event_on_upgrade(...)` rewrites the row's title/body/score/context/next_action/fired_at in place.
- `router.route_event` now: if an existing event exists, compare `score_at_fire` against the new candidate; if `new >= old + upgrade_delta` (default **5 points**, tunable via `alerts.metadata.upgrade_delta_score`), upgrade the row **without re-dispatching channels** (no notification spam; the rewrite is for record/UI/replay purposes only). If not materially stronger, skip as before.

## 6. Secrets out of alerts.yaml  (Tier C #10)

`configs/alerts.yaml` contained a hard-coded SMTP app password as the fallback default for `${SMTP_PASSWORD:-...}`. Anyone with repo access had live credentials. Fix:

- All secret fallbacks stripped: `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_ADDR`, `ALERT_EMAIL_TO_1` now resolve from env only. If the env var is unset, the value is the empty string, which the startup validator (see #7) catches as a hard error and refuses to start.
- **Action required by the operator**: rotate the Gmail app-password that was previously committed. Treat it as compromised.
- Added a header comment on the SMTP block documenting the env-only contract.

## 7a. Windows desktop toast + sound channel  (new)

Added a `windows_toast` alert channel that fires a Windows 10/11 toast notification and plays a system sound when an alert is routed to the `high_signal` topic (BUY_SELECTED, SELL_STOP, SELL_FAILED_BREAKOUT, SELL_TIMEOUT, etc.). The implementation has no pip dependencies — sound via stdlib `winsound`, toast via PowerShell's native `Windows.UI.Notifications` API.

Files: `backend/app/alerts/channels/windows_toast.py` (new), `backend/app/alerts/channels/dispatcher.py`, `backend/app/alerts/router.py`, `backend/app/core/config.py`, `backend/app/api/v1/settings.py`, `configs/alerts.yaml`.

Two layers of on/off control:

- **Config-file flag** (`alerts.delivery.windows_toast.enabled: true|false` in `alerts.yaml`, also respects `${WINDOWS_TOAST_ENABLED}` env var). Survives restarts. This is the primary switch.
- **Runtime toggle** via HTTP without restarting: `POST /api/v1/settings/windows-toast {"enabled": true}` (or `false`, or omit `enabled` to toggle). `GET /api/v1/settings/windows-toast` returns current state. Effective state is `config_enabled AND runtime_enabled` — so the API can only silence a config-enabled channel, not enable one that's turned off in YAML.

Behaviour on non-Windows hosts (e.g. dev machines): the channel returns a `SKIPPED` delivery with `{"reason": "NOT_WINDOWS"}` — no errors, no red herrings.

Config knobs: `play_sound` (default true), `sound_alias` (winsound alias name, default `SystemAsterisk`), `app_id` (label shown in the Action Center, default `"Momentum Alerts"`).

## 7. Fail-loud config validation  (Tier C — new)

Added `backend/app/core/config_validation.py`:

- `validate_startup_config(cfg) -> list[warnings]`, raising `ConfigValidationError` on hard failures with every error aggregated into a single message pointing at the offending YAML key.

Hard errors:
- `alerts.delivery.email.enabled=true` with missing SMTP host/port/username/password/from_addr.
- `alerts.delivery.email.enabled=true` with no recipients.
- No enabled buy profile (nothing can be bought).
- Missing `strategy.profiles.sell.common` or its `stop` block.
- `scheduler.enabled=true` with non-positive `interval_minutes`.

Soft warnings (logged, don't abort):
- ntfy enabled with blank server or blank topics.
- Email recipients that don't look like email addresses.
- `max_open_positions` or `top_n_per_run` ≤ 0.
- News enabled with no provider enabled.

Wired into `main.py`'s `lifespan` immediately after `config.load()`. A `ConfigValidationError` aborts startup; an unexpected error in the validator itself is logged and suppressed (defensive — a validator bug should never wedge a production deploy).

Smoke-tested against both a failure stub (missing SMTP creds + no enabled buy profile) and a happy-path stub; both branches behave as expected.

---

## What is explicitly **out** of this pass

Per the operator's directive ("fix all the code issues within the application first, then we think about context layer"):

- No LLM/Claude API integration.
- No n8n integration.
- No news-validation layer beyond the existing `news:` config block.
- No brokerage auto-execution. Positions remain user-managed; the system only produces BUY_SELECTED and SELL_* signals.

These are reasonable next steps, but they are additive and should layer on top of the now-stabilised core.

## Remaining items from Analysis_Report.md not addressed here

- **Tier B #7** (position sizing as fixed-R) — requires schema change to `positions` and a portfolio-capital input from the user. Out of scope for this pass.
- **Tier C #9** (intraday adapter consolidation) — the existing yahoo/nse/mixed adapter path works; swapping to a single-source intraday feed is a larger project.
- **Tier D items** (frontend polish, dashboard UX) — not a code-correctness issue and not on the critical path to the 4–6% realistic return target.
