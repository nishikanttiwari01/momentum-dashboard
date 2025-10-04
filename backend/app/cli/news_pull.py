# backend/app/cli/news_pull.py
from __future__ import annotations

import argparse
import json
import os
import sys
import subprocess
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, date, timezone
from pathlib import Path
from typing import Iterable, Optional, Tuple, List, Dict, Any
import time
import uuid

# Fast API models you generated from OpenAPI
from app.schemas.generated.models import NewsIngestBatch

# Your config loader
from app.core.config import load as load_settings

log = logging.getLogger(__name__)

# Reuse your screener snapshot access
from app.repos.parquet.scores_repo import ScoresRepo
from app.pipeline.news_provider import _build_batch


# ──────────────────────────────────────────────────────────────────────────────
# Logging helpers
# ──────────────────────────────────────────────────────────────────────────────

def _configure_logging(default_level: str = "INFO") -> None:
    """
    Configure root logging if the app hasn't set it up already.
    Respects LOG_LEVEL env if set (e.g. DEBUG, INFO).
    """
    root = logging.getLogger()
    if not root.handlers:
        level_name = os.getenv("LOG_LEVEL", default_level).upper()
        level = getattr(logging, level_name, logging.INFO)
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        log.debug("logging.configured", extra={"level": level_name})


def _runid() -> str:
    """Stable-ish correlation id for a single CLI invocation."""
    # One per process
    if not hasattr(_runid, "_id"):
        setattr(_runid, "_id", uuid.uuid4().hex[:12])
    return getattr(_runid, "_id")


def _timeit_start() -> float:
    return time.perf_counter()


def _timeit_done(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000.0, 2)  # ms


def _log_exception(context: str, **extra_kv: Any) -> None:
    # Always include correlation id
    extra_kv = {"run_id": _runid(), **extra_kv}
    log.exception(context, extra=extra_kv)


# ──────────────────────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────────────────────

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _parse_since_expr(expr: str) -> int:
    """
    Return minutes for simple "10m", "2h", "1d". Defaults to minutes if no suffix.
    """
    s = expr.strip().lower()
    try:
        if s.endswith("m"):
            val = int(s[:-1])
        elif s.endswith("h"):
            val = int(float(s[:-1]) * 60)
        elif s.endswith("d"):
            val = int(float(s[:-1]) * 1440)
        else:
            val = int(float(s))
        log.debug("since_expr.parsed", extra={"expr": expr, "minutes": val, "run_id": _runid()})
        return val
    except Exception as e:
        _log_exception("since_expr.parse_failed", expr=expr)
        raise

def _read_json(path: Path) -> Any:
    t0 = _timeit_start()
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    log.debug("json.read_ok", extra={"path": str(path), "ms": _timeit_done(t0), "run_id": _runid()})
    return data

def _to_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

def _unique_preserve(seq: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for s in seq:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out

def _stderr(msg: str) -> None:
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


# ──────────────────────────────────────────────────────────────────────────────
# Cohort selection (watchlist+top movers+score threshold)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class IntradayCohorts:
    watchlist: List[str]
    top_gainers: List[str]
    top_losers: List[str]
    high_score: List[str]

    def union(self) -> List[str]:
        unioned = _unique_preserve(
            list(self.watchlist) + list(self.top_gainers) + list(self.top_losers) + list(self.high_score)
        )
        log.debug(
            "cohorts.union",
            extra={
                "watchlist": len(self.watchlist),
                "top_gainers": len(self.top_gainers),
                "top_losers": len(self.top_losers),
                "high_score": len(self.high_score),
                "union": len(unioned),
                "run_id": _runid(),
            },
        )
        return unioned


def _load_watchlist_symbols(path: Optional[str]) -> List[str]:
    if not path:
        log.debug("watchlist.skip_none", extra={"run_id": _runid()})
        return []
    p = Path(path).expanduser()
    if not p.exists():
        _stderr(f"[warn] watchlist file not found: {p}")
        log.warning("watchlist.not_found", extra={"path": str(p), "run_id": _runid()})
        return []
    symbols: List[str] = []
    t0 = _timeit_start()
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        symbols.append(s)
    symbols = _unique_preserve(symbols)
    log.info("watchlist.loaded", extra={"path": str(p), "count": len(symbols), "ms": _timeit_done(t0), "run_id": _runid()})
    return symbols


def _select_from_scores_latest(
    *,
    top_gainers_count: int,
    top_losers_count: int,
    min_abs_change_pct: float,
    score_min: Optional[float],
    score_type: str = "full",   # "full" | "basic"
    max_symbols_score_bucket: Optional[int] = None,
) -> Tuple[List[str], List[str], List[str], Optional[str], Optional[str]]:
    """
    Use ScoresRepo to read the latest snapshot (intraday today or daily fallback).
    Returns (gainers, losers, high_score, run_id_used, as_of_used).
    """
    repo = ScoresRepo()
    log.info(
        "scores.read_begin",
        extra={
            "sort": "pct_today.desc",
            "min_abs_change_pct": float(min_abs_change_pct),
            "top_gainers_count": int(top_gainers_count),
            "top_losers_count": int(top_losers_count),
            "score_min": None if score_min is None else float(score_min),
            "score_type": score_type,
            "max_symbols_score_bucket": max_symbols_score_bucket,
            "run_id": _runid(),
        },
    )

    # Pull a large page to avoid paging loops for personal use
    page, per_page = 1, 50000

    # Base columns we need. ScoresRepo will synthesize pct_today from change_pct if needed.
    columns = ["symbol", "score_full", "score_basic", "score", "pct_today", "change_pct"]

    t0 = _timeit_start()
    rows, total, rid, as_of = repo.read(
        run_id=None,
        as_of_str=None,
        filters={},  # rank all
        sort="pct_today.desc",  # fastest to pick top movers
        page=page,
        per_page=per_page,
        columns=columns,
    )
    log.info(
        "scores.read_done",
        extra={"rows": len(rows), "total": total, "rid": rid, "as_of": as_of, "ms": _timeit_done(t0), "run_id": _runid()},
    )

    # Normalize pct_today values and collect symbols with changes
    movers_pos: List[Tuple[str, float]] = []
    movers_neg: List[Tuple[str, float]] = []

    for r in rows:
        sym = r.get("symbol")
        pct = r.get("pct_today")
        if sym is None or pct is None:
            continue
        try:
            fp = float(pct)
        except Exception:
            continue
        if abs(fp) < float(min_abs_change_pct):
            continue
        if fp >= 0:
            movers_pos.append((sym, fp))
        else:
            # keep original line (do not remove) but guard it so it never crashes on undefined names
            try:
                log.info("news.run_backfill_provider_internal", extra={"trading_day": trading_day.isoformat(), "since_minutes": since_minutes, "anchor": at_iso})
            except Exception:
                log.debug("movers.neg_marker", extra={"symbol": sym, "pct": fp, "run_id": _runid()})
            movers_neg.append((sym, fp))

    # Top-N by absolute position already sorted desc by pct_today
    top_gainers = [s for s, _ in movers_pos[: max(0, int(top_gainers_count))]]
    # For losers, we want most negative (rows sorted desc overall); sort losers ascending
    movers_neg_sorted = sorted(movers_neg, key=lambda t: t[1])  # most negative first
    top_losers = [s for s, _ in movers_neg_sorted[: max(0, int(top_losers_count))]]

    # High score cohort
    high_score: List[str] = []
    if score_min is not None:
        score_field = "score_full" if score_type == "full" else "score_basic"
        filters = {(score_field, "gte"): float(score_min)}
        t1 = _timeit_start()
        rows_score, total_s, _, _ = repo.read(
            run_id=rid,                # bind to same snapshot when possible
            as_of_str=as_of,
            filters=filters,
            sort=f"{score_field}.desc",
            page=1,
            per_page=max_symbols_score_bucket or 50000,
            columns=["symbol", score_field],
        )
        high_score = [r["symbol"] for r in rows_score if r.get("symbol")]
        log.info(
            "scores.high_bucket",
            extra={"field": score_field, "min": float(score_min), "count": len(high_score), "ms": _timeit_done(t1), "run_id": _runid()},
        )

    log.info(
        "cohorts.selected",
        extra={
            "top_gainers": len(top_gainers),
            "top_losers": len(top_losers),
            "high_score": len(high_score),
            "rid": rid,
            "as_of": as_of,
            "run_id": _runid(),
        },
    )

    return top_gainers, top_losers, _unique_preserve(high_score), rid, as_of


def build_intraday_symbol_set(
    *,
    watchlist_file: Optional[str],
    top_gainers_count: int,
    top_losers_count: int,
    min_abs_change_pct: float,
    score_min: Optional[float],
    score_type: str,
    max_symbols_score_bucket: Optional[int],
) -> Tuple[IntradayCohorts, Optional[str], Optional[str]]:
    t0 = _timeit_start()
    watchlist = _load_watchlist_symbols(watchlist_file)
    gainers, losers, hi, rid, as_of = _select_from_scores_latest(
        top_gainers_count=top_gainers_count,
        top_losers_count=top_losers_count,
        min_abs_change_pct=min_abs_change_pct,
        score_min=score_min,
        score_type=score_type,
        max_symbols_score_bucket=max_symbols_score_bucket,
    )
    cohorts = IntradayCohorts(
        watchlist=watchlist,
        top_gainers=gainers,
        top_losers=losers,
        high_score=hi,
    )
    log.info(
        "symbolset.built",
        extra={
            "watchlist": len(watchlist),
            "gainers": len(gainers),
            "losers": len(losers),
            "high_score": len(hi),
            "rid": rid,
            "as_of": as_of,
            "ms": _timeit_done(t0),
            "run_id": _runid(),
        },
    )
    return cohorts, rid, as_of


# ──────────────────────────────────────────────────────────────────────────────
# Provider execution (pluggable external pipeline) + ingest POST
# ──────────────────────────────────────────────────────────────────────────────

def _run_provider_cmd(
    *,
    cmd: str,
    symbols: List[str],
    since_minutes: int,
    at_datetime_iso: Optional[str],
    extra_env: Dict[str, str],
) -> NewsIngestBatch:
    """
    Execute an external provider command that prints a JSON NewsIngestBatch to stdout.
    The provider is expected to:
      - accept --symbols <csv> and --since <minutes>
      - optionally accept --at <iso8601> to align with backfill day
      - print normalized JSON per your OpenAPI schema (NewsIngestBatch).
    """
    if not cmd:
        raise RuntimeError("news.pipeline.provider_cmd not configured in default.yaml")

    args = [cmd, "--symbols", ",".join(symbols), "--since", str(int(since_minutes))]
    if at_datetime_iso:
        args += ["--at", at_datetime_iso]

    env = os.environ.copy()
    env.update(extra_env or {})
    # Allow simple "python path/to/script.py" too
    if " " in args[0] and not Path(args[0]).exists():
        # Split user's shell-like command
        args = args[0].split(" ") + args[1:]

    log.info(
        "provider.exec",
        extra={
            "cmd": args[0],
            "args_count": len(args) - 1,
            "symbols": len(symbols),
            "since_minutes": since_minutes,
            "at": at_datetime_iso,
            "env_injected": sorted(list((extra_env or {}).keys())),
            "run_id": _runid(),
        },
    )

    t0 = _timeit_start()
    proc = subprocess.run(
        args,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    ms = _timeit_done(t0)

    if proc.returncode != 0:
        _stderr(f"[error] provider failed ({proc.returncode}): {proc.stderr.strip()}")
        log.error(
            "provider.failed",
            extra={
                "returncode": proc.returncode,
                "stderr_len": len(proc.stderr or ""),
                "stdout_len": len(proc.stdout or ""),
                "ms": ms,
                "run_id": _runid(),
            },
        )
        raise RuntimeError("provider_cmd_failed")

    out = proc.stdout.strip()
    log.info(
        "provider.ok",
        extra={
            "stdout_len": len(out),
            "stderr_len": len((proc.stderr or "").strip()),
            "ms": ms,
            "run_id": _runid(),
        },
    )
    if not out:
        log.error("provider.no_output", extra={"ms": ms, "run_id": _runid()})
        raise RuntimeError("provider_cmd produced no output")

    try:
        batch = NewsIngestBatch.model_validate_json(out)
        log.info("provider.batch_parsed", extra={"items": len(batch.items), "run_id": _runid()})
    except Exception as e:
        _stderr(f"[error] provider returned invalid JSON for NewsIngestBatch: {e}\n--- provider stdout ---\n{out[:1000]}")
        _log_exception("provider.invalid_json", stdout_preview=out[:250])
        raise

    return batch


def _http_post_json(url: str, payload: dict, timeout: int = 30) -> Tuple[int, str]:
    """
    Post JSON without adding a heavy HTTP dependency. Uses urllib from stdlib.
    """
    import urllib.request
    import urllib.error

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        t0 = _timeit_start()
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.getcode()
            body = resp.read().decode("utf-8", errors="ignore")
            ms = _timeit_done(t0)
            log.info("http.post_ok", extra={"url": url, "code": code, "bytes": len(body or ""), "ms": ms, "run_id": _runid()})
            return code, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        log.error("http.post_http_error", extra={"url": url, "code": e.code, "bytes": len(body or ""), "run_id": _runid()})
        return e.code, body
    except Exception as e:
        _log_exception("http.post_exception", url=url)
        return 0, repr(e)


def _ingest_batch_via_api(api_base: str, batch: NewsIngestBatch) -> None:
    url = api_base.rstrip("/") + "/api/v1/news/ingest"
    log.info("ingest.begin", extra={"url": url, "items": len(batch.items), "run_id": _runid()})
    code, body = _http_post_json(url, json.loads(batch.model_dump_json()))
    if code not in (200, 202):
        _stderr(f"[error] ingest failed ({code}): {body.strip()}")
        log.error("ingest.failed", extra={"code": code, "body_len": len(body or ""), "run_id": _runid()})
        raise RuntimeError("ingest_failed")
    log.info("ingest.ok", extra={"code": code, "items": len(batch.items), "run_id": _runid()})


# ──────────────────────────────────────────────────────────────────────────────
# Intraday & Backfill runners
# ──────────────────────────────────────────────────────────────────────────────

def run_intraday(
    *,
    api_base: str,
    watchlist_file: Optional[str],
    since_expr: str,
    top_gainers: int,
    top_losers: int,
    min_abs_change_pct: float,
    score_min: Optional[float],
    score_type: str,
    max_symbols_score_bucket: Optional[int],
    provider_cmd: str,
    extra_env: Dict[str, str],
    symbol_limit: Optional[int],
) -> None:
    log.info(
        "news.run_intraday_start",
        extra={
            "since_expr": since_expr,
            "top_gainers": top_gainers,
            "top_losers": top_losers,
            "min_abs_change_pct": min_abs_change_pct,
            "score_min": score_min,
            "symbol_limit": symbol_limit,
            "provider_cmd": provider_cmd,
            "run_id": _runid(),
        },
    )
    since_minutes = _parse_since_expr(since_expr)
    cohorts, rid, as_of = build_intraday_symbol_set(
        watchlist_file=watchlist_file,
        top_gainers_count=top_gainers,
        top_losers_count=top_losers,
        min_abs_change_pct=min_abs_change_pct,
        score_min=score_min,
        score_type=score_type,
        max_symbols_score_bucket=max_symbols_score_bucket,
    )
    symbols = cohorts.union()
    if symbol_limit is not None and len(symbols) > symbol_limit:
        log.debug("symbolset.truncated", extra={"before": len(symbols), "after": symbol_limit, "run_id": _runid()})
        symbols = symbols[:symbol_limit]
    if not symbols:
        log.info("news.run_intraday_no_symbols", extra={"run_id": _runid()})
        _stderr("[info] no symbols selected for intraday run; exiting")
        return
    log.info("news.run_intraday_execute", extra={"symbols": len(symbols), "rid": rid, "as_of": as_of, "run_id": _runid()})
    _stderr(
        f"[info] intraday selection: {len(symbols)} symbols (gainers={len(cohorts.top_gainers)}, "
        f"losers={len(cohorts.top_losers)}, high_score={len(cohorts.high_score)}, watchlist={len(cohorts.watchlist)})"
    )
    t0 = _timeit_start()
    batch = _run_provider_cmd(
        cmd=provider_cmd,
        symbols=symbols,
        since_minutes=since_minutes,
        at_datetime_iso=None,
        extra_env=extra_env,
    )
    log.info("news.run_intraday_provider_done", extra={"items": len(batch.items), "ms": _timeit_done(t0), "run_id": _runid()})
    _ingest_batch_via_api(api_base, batch)
    log.info("news.run_intraday_ingested", extra={"items": len(batch.items), "run_id": _runid()})
    _stderr(f"[ok] ingested {len(batch.items)} news clusters")

def run_backfill(
    *,
    api_base: str,
    trading_day: date,
    provider_cmd: Optional[str],
    extra_env: Dict[str, str],
    symbols_all_file: Optional[str],
    symbol_limit: Optional[int],
) -> None:
    """
    log.info("news.run_backfill_start", extra={"trading_day": trading_day.isoformat(), "provider_cmd_raw": provider_cmd})
    Backfill for a specific trading day (IST). You can pass a precomputed symbol list (file),
    otherwise it will take all symbols from the latest daily snapshot for that day.
    """
    log.info(
        "news.run_backfill_start",
        extra={"trading_day": trading_day.isoformat(), "provider_cmd_raw": provider_cmd, "run_id": _runid()},
    )
    settings = load_settings()
    if symbols_all_file:
        symbols = _load_watchlist_symbols(symbols_all_file)
    else:
        repo = ScoresRepo()
        t0 = _timeit_start()
        _, as_of = repo.latest_run()
        rows, total, rid, as_of = repo.read(
            run_id=None,
            as_of_str=None,
            filters={},
            sort="symbol.asc",
            page=1,
            per_page=50000,
            columns=["symbol", "last"],
        )
        ms = _timeit_done(t0)
        symbols = [r["symbol"] for r in rows if r.get("symbol")]
        log.info(
            "news.run_backfill_symbols_loaded",
            extra={"rid": rid, "as_of": as_of, "count": len(symbols), "ms": ms, "run_id": _runid()},
        )
    if symbol_limit is not None and len(symbols) > symbol_limit:
        log.debug("backfill.symbolset.truncated", extra={"before": len(symbols), "after": symbol_limit, "run_id": _runid()})
        symbols = symbols[:symbol_limit]
    log.info(
        "news.run_backfill_symbols_resolved",
        extra={"trading_day": trading_day.isoformat(), "symbol_count": len(symbols), "run_id": _runid()},
    )
    if not symbols:
        _stderr("[info] no symbols found for backfill; exiting")
        log.info("news.run_backfill_no_symbols", extra={"trading_day": trading_day.isoformat(), "run_id": _runid()})
        return
    tz = settings.news.trading_timezone or "Asia/Kolkata"
    try:
        import zoneinfo
        ist = zoneinfo.ZoneInfo(tz)
    except Exception:
        ist = None
        log.warning("tz.zoneinfo_unavailable", extra={"tz": tz, "run_id": _runid()})
    if ist is not None:
        anchor_dt = datetime(trading_day.year, trading_day.month, trading_day.day, 9, 0, 0, tzinfo=ist)
    else:
        anchor_dt = datetime(trading_day.year, trading_day.month, trading_day.day, 9, 0, 0)
    at_iso = anchor_dt.isoformat()
    since_minutes = 1440
    provider_cmd_clean = (provider_cmd or "").strip() or None
    log.info(
        "news.run_backfill_provider_resolved",
        extra={
            "trading_day": trading_day.isoformat(),
            "provider_cmd": provider_cmd_clean or "internal",
            "since_minutes": since_minutes,
            "anchor": at_iso,
            "run_id": _runid(),
        },
    )
    _stderr(f"[info] backfill {trading_day.isoformat()} for {len(symbols)} symbols")
    if provider_cmd_clean:
        log.info(
            "news.run_backfill_provider_exec",
            extra={"trading_day": trading_day.isoformat(), "provider_cmd": provider_cmd_clean, "run_id": _runid()},
        )
        t0 = _timeit_start()
        batch = _run_provider_cmd(
            cmd=provider_cmd_clean,
            symbols=symbols,
            since_minutes=since_minutes,
            at_datetime_iso=at_iso,
            extra_env=extra_env,
        )
        log.info(
            "news.run_backfill_provider_done",
            extra={
                "trading_day": trading_day.isoformat(),
                "provider_cmd": provider_cmd_clean,
                "item_count": len(batch.items),
                "ms": _timeit_done(t0),
                "run_id": _runid(),
            },
        )
    else:
        log.info(
            "news.run_backfill_provider_internal",
            extra={"trading_day": trading_day.isoformat(), "since_minutes": since_minutes, "anchor": at_iso, "run_id": _runid()},
        )
        t0 = _timeit_start()
        batch = _build_batch(symbols=symbols, since_minutes=since_minutes, anchor=anchor_dt)
        log.info(
            "news.run_backfill_provider_internal_done",
            extra={"trading_day": trading_day.isoformat(), "item_count": len(batch.items), "ms": _timeit_done(t0), "run_id": _runid()},
        )
        _stderr(f"[info] provider internal pipeline (since={since_minutes}m, anchor={at_iso})")
    _ingest_batch_via_api(api_base, batch)
    log.info(
        "news.run_backfill_ingested",
        extra={"trading_day": trading_day.isoformat(), "item_count": len(batch.items), "run_id": _runid()},
    )
    _stderr(f"[ok] ingested {len(batch.items)} news clusters for {trading_day.isoformat()}")

def _settings_defaults() -> Dict[str, Any]:
    s = load_settings()
    news = s.news
    intr = (news.run_modes or {}).get("intraday", {})
    cohorts = (intr or {}).get("cohorts", {})
    top = cohorts.get("top_movers", {}) if cohorts else {}
    score = cohorts.get("score_threshold", {}) if cohorts else {}
    fetch = (intr or {}).get("fetch", {}) if intr else {}
    return {
        "since": fetch.get("since", "10m"),
        "top_gainers": int(top.get("top_gainers_count", 10) or 10),
        "top_losers": int(top.get("top_losers_count", 10) or 10),
        "min_abs_change_pct": float(top.get("min_abs_change_pct", 1.0) or 1.0),
        "score_min": float(score.get("min_score", 70)) if score.get("include", True) else None,
        "score_type": str(score.get("score_type", "full") or "full"),
        "max_symbols_score_bucket": int(score.get("max_symbols", 100) or 100),
        "symbol_limit": int((intr or {}).get("fetch", {}).get("max_symbols_per_run", 250) or 250),
    }

def main(argv: Optional[List[str]] = None) -> int:
    _configure_logging()  # safe no-op if app already configured
    d = _settings_defaults()
    s = load_settings()
    api_base_default = f"http://{s.server.host}:{s.server.port}"

    parser = argparse.ArgumentParser(prog="news-pull", description="Pull intraday/backfill news and ingest to API.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_intra = sub.add_parser("intraday", help="Pull intraday news for watchlist + top movers + high-score symbols.")
    p_intra.add_argument("--api-base", default=api_base_default, help="API base URL (default: server host/port).")
    p_intra.add_argument("--watchlist-file", default=os.getenv("WATCHLIST_FILE"), help="Optional path to a newline-delimited symbol list.")
    p_intra.add_argument("--since", default=d["since"], help="Lookback window, e.g., 10m / 30m / 2h.")
    p_intra.add_argument("--top-gainers", type=int, default=d["top_gainers"])
    p_intra.add_argument("--top-losers", type=int, default=d["top_losers"])
    p_intra.add_argument("--min-abs-change-pct", type=float, default=d["min_abs_change_pct"])
    p_intra.add_argument("--score-min", type=float, default=(d["score_min"] if d["score_min"] is not None else 70))
    p_intra.add_argument("--score-type", choices=["full", "basic"], default=d["score_type"])
    p_intra.add_argument("--max-symbols-score-bucket", type=int, default=d["max_symbols_score_bucket"])
    p_intra.add_argument("--symbol-limit", type=int, default=d["symbol_limit"])
    p_intra.add_argument("--provider-cmd", default=os.getenv("NEWS_PROVIDER_CMD") or (s.features.get("news", {}) if isinstance(s.features, dict) else None),
                        help="External provider command that prints NewsIngestBatch JSON. You can also set NEWS_PROVIDER_CMD env.")
    p_intra.add_argument("--env", nargs="*", default=[], help="Inject env to provider as KEY=VALUE.")

    p_back = sub.add_parser("backfill", help="Backfill T-day news across all symbols.")
    p_back.add_argument("--api-base", default=api_base_default)
    p_back.add_argument("--day", required=True, help="Trading day YYYY-MM-DD (IST).")
    p_back.add_argument("--provider-cmd", default=os.getenv("NEWS_PROVIDER_CMD"),
                        help="External provider command that prints NewsIngestBatch JSON. You can also set NEWS_PROVIDER_CMD env.")
    p_back.add_argument("--env", nargs="*", default=[])
    p_back.add_argument("--symbols-file", help="Optional newline-delimited list of all symbols for backfill.")
    p_back.add_argument("--symbol-limit", type=int, default=None)

    args = parser.parse_args(argv)

    log.info("cli.args", extra={"cmd": args.cmd, "run_id": _runid()})

    # Parse extra env pairs
    extra_env: Dict[str, str] = {}
    for kv in (args.env or []):
        if "=" in kv:
            k, v = kv.split("=", 1)
            extra_env[k] = v
    if extra_env:
        log.debug("cli.env_injected", extra={"keys": sorted(list(extra_env.keys())), "run_id": _runid()})

    if args.cmd == "intraday":
        if not args.provider_cmd:
            _stderr("[error] --provider-cmd not set and NEWS_PROVIDER_CMD not present")
            log.error("cli.missing_provider", extra={"mode": "intraday", "run_id": _runid()})
            return 2
        try:
            run_intraday(
                api_base=args.api_base,
                watchlist_file=args.watchlist_file,
                since_expr=args.since,
                top_gainers=args.top_gainers,
                top_losers=args.top_losers,
                min_abs_change_pct=args.min_abs_change_pct,
                score_min=args.score_min,
                score_type=args.score_type,
                max_symbols_score_bucket=args.max_symbols_score_bucket,
                provider_cmd=str(args.provider_cmd),
                extra_env=extra_env,
                symbol_limit=args.symbol_limit,
            )
            return 0
        except Exception:
            _log_exception("intraday.unhandled_exception")
            return 1

    if args.cmd == "backfill":
        if not args.provider_cmd:
            _stderr("[error] --provider-cmd not set and NEWS_PROVIDER_CMD not present")
            log.error("cli.missing_provider", extra={"mode": "backfill", "run_id": _runid()})
            return 2
        try:
            y, m, dday = map(int, args.day.split("-"))
            trading_day = date(y, m, dday)
        except Exception:
            _stderr("[error] invalid --day value; expected YYYY-MM-DD")
            log.error("cli.bad_day_arg", extra={"day": getattr(args, "day", None), "run_id": _runid()})
            return 2
        try:
            run_backfill(
                api_base=args.api_base,
                trading_day=trading_day,
                provider_cmd=str(args.provider_cmd),
                extra_env=extra_env,
                symbols_all_file=args.symbols_file,
                symbol_limit=args.symbol_limit,
            )
            return 0
        except Exception:
            _log_exception("backfill.unhandled_exception", trading_day=trading_day.isoformat())
            return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
