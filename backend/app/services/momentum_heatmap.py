from __future__ import annotations

import csv
import io
import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from zoneinfo import ZoneInfo

from app.core import config as app_config
from app.schemas.generated.models import (
    AdvanceDeclineSummary,
    MomentumHeatmapConstituent,
    MomentumHeatmapResponse,
    MomentumHeatmapSector,
)

log = logging.getLogger(__name__)

_IST = ZoneInfo("Asia/Kolkata")
_UTC = ZoneInfo("UTC")

HISTORY_LOOKBACK_DAYS = 65
WEEK_OFFSET = 5
MONTH_OFFSET = 21
AVG_TURNOVER_WINDOW = 20
CACHE_TTL_SECONDS = 300

HISTORY_URL_PATTERNS = (
    "https://archives.nseindia.com/content/indices/ind_close_all_{date}.csv",
    "https://nsearchives.nseindia.com/content/indices/ind_close_all_{date}.csv",
    "https://www1.nseindia.com/archives/indices/ind_close_all_{date}.csv",
)


@dataclass(frozen=True)
class IndexSpec:
    index_name: str
    symbol: str


@dataclass
class AdvanceDeclineCounts:
    advancers: int
    decliners: int
    unchanged: int


@dataclass
class ConstituentSnapshot:
    symbol: str
    name: Optional[str]
    last_price: Optional[float]
    change_pct: Optional[float]
    change_value: Optional[float]
    turnover_cr: Optional[float]
    weight_pct: Optional[float]


@dataclass
class IndexSnapshot:
    spec: IndexSpec
    last: float
    percent_change: Optional[float]
    previous_close: Optional[float]
    timestamp: datetime
    turnover_cr: Optional[float]
    advance: Optional[AdvanceDeclineCounts]
    constituents: List[ConstituentSnapshot]


SECTOR_INDICES: tuple[IndexSpec, ...] = (
    IndexSpec("NIFTY BANK", "NIFTYBANK"),
    IndexSpec("NIFTY FIN SERVICE", "NIFTYFIN"),
    IndexSpec("NIFTY IT", "NIFTYIT"),
    IndexSpec("NIFTY PHARMA", "NIFTYPHARMA"),
    IndexSpec("NIFTY AUTO", "NIFTYAUTO"),
    IndexSpec("NIFTY FMCG", "NIFTYFMCG"),
    IndexSpec("NIFTY METAL", "NIFTYMETAL"),
    IndexSpec("NIFTY REALTY", "NIFTYREALTY"),
    IndexSpec("NIFTY ENERGY", "NIFTYENERGY"),
    IndexSpec("NIFTY MEDIA", "NIFTYMEDIA"),
    IndexSpec("NIFTY PSU BANK", "NIFTYPSUBANK"),
    IndexSpec("NIFTY PRIVATE BANK", "NIFTYPVTBANK"),
    IndexSpec("NIFTY OIL & GAS", "NIFTYOILGAS"),
    IndexSpec("NIFTY CONSUMER DURABLES", "NIFTYCD"),
    IndexSpec("NIFTY SERVICES SECTOR", "NIFTYSERV"),
)


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _safe_div(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator in (None, 0):
        return None
    try:
        return numerator / denominator
    except ZeroDivisionError:
        return None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _tz_now() -> datetime:
    return datetime.now(tz=_IST)


def _parse_timestamp(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%m-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d-%b-%Y", "%d-%m-%Y"):
        try:
            dt = datetime.strptime(text, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_IST)
            return dt
        except ValueError:
            continue
    return None


class NSEIndexClient:
    BASE_URL = "https://www.nseindia.com/api/equity-stockIndices"

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self._session = session or self._create_session()
        self._lock = threading.Lock()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        headers = {
            "User-Agent": os.getenv(
                "MOMENTUM_HEATMAP_UA",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com/",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
        session.headers.update(headers)
        try:
            session.get("https://www.nseindia.com/", timeout=(8, 12))
        except Exception:
            log.debug("MomentumHeatmapService: warm-up request to nseindia.com failed")
        return session

    def fetch_index_snapshot(self, spec: IndexSpec) -> Optional[IndexSnapshot]:
        params = {"index": spec.index_name}
        try:
            with self._lock:
                resp = self._session.get(self.BASE_URL, params=params, timeout=(8, 12))
        except Exception as exc:
            log.warning("Failed to fetch NSE index snapshot", extra={"index": spec.index_name, "err": str(exc)[:200]})
            return None

        if resp.status_code != 200:
            log.warning(
                "Unexpected status while fetching NSE index snapshot",
                extra={"index": spec.index_name, "status": resp.status_code},
            )
            return None

        try:
            payload = resp.json()
        except ValueError as exc:
            log.warning("Invalid JSON for NSE index snapshot", extra={"index": spec.index_name, "err": str(exc)[:200]})
            return None

        last = _to_float(payload.get("last") or payload.get("close") or payload.get("current"))
        prev_close = _to_float(payload.get("previousClose") or payload.get("prevClose"))
        if last is None:
            log.debug("Missing 'last' price for index snapshot", extra={"index": spec.index_name})
            return None

        percent_change = _to_float(payload.get("percentChange") or payload.get("pChange"))
        timestamp = _parse_timestamp(payload.get("timestamp") or payload.get("lastUpdateTime"))
        if timestamp is None:
            timestamp = _tz_now()

        advance_obj = payload.get("advance") or payload.get("advances")
        advance = None
        if isinstance(advance_obj, dict):
            advance = AdvanceDeclineCounts(
                advancers=int(_to_float(advance_obj.get("adv")) or _to_float(advance_obj.get("advances")) or 0),
                decliners=int(_to_float(advance_obj.get("dec")) or _to_float(advance_obj.get("declines")) or 0),
                unchanged=int(_to_float(advance_obj.get("unch")) or _to_float(advance_obj.get("unchanged")) or 0),
            )

        raw_constituents = payload.get("data") or []
        constituents = self._parse_constituents(raw_constituents)
        turnover_cr = payload.get("turnover") or payload.get("totalTradedValue")
        turnover_cr = _to_float(turnover_cr)
        if turnover_cr is None and constituents:
            turnover_sum = sum(c.turnover_cr or 0 for c in constituents)
            turnover_cr = turnover_sum if turnover_sum > 0 else None

        return IndexSnapshot(
            spec=spec,
            last=last,
            percent_change=percent_change,
            previous_close=prev_close,
            timestamp=timestamp,
            turnover_cr=turnover_cr,
            advance=advance,
            constituents=constituents,
        )

    def _parse_constituents(self, rows: Iterable[Dict[str, Any]]) -> List[ConstituentSnapshot]:
        items: List[ConstituentSnapshot] = []
        for row in rows:
            symbol = (row.get("symbol") or row.get("SYMBOL") or "").strip()
            if not symbol:
                continue
            name_val = row.get("meta") or row.get("companyName") or row.get("identifier") or row.get("name")
            name = name_val.strip() if isinstance(name_val, str) else None
            last_price = _to_float(
                row.get("lastPrice") or row.get("ltp") or row.get("close") or row.get("last_traded_price")
            )
            change_pct = _to_float(
                row.get("perChange")
                or row.get("pChange")
                or row.get("percentChange")
                or row.get("iislPercChange")
            )
            change_val = _to_float(row.get("netChange") or row.get("change") or row.get("dayChange"))
            turnover_val = _to_float(
                row.get("totalTradedValue") or row.get("turnover") or row.get("trdVal") or row.get("value")
            )
            turnover_cr = turnover_val / 1e7 if turnover_val and turnover_val > 0 else None
            weight_pct = _to_float(row.get("weightage") or row.get("weight"))
            items.append(
                ConstituentSnapshot(
                    symbol=symbol,
                    name=name,
                    last_price=last_price,
                    change_pct=change_pct,
                    change_value=change_val,
                    turnover_cr=turnover_cr,
                    weight_pct=weight_pct,
                )
            )
        return items

    def download_eod_csv(self, target_date: date) -> Optional[str]:
        token = target_date.strftime("%d%m%Y")
        for template in HISTORY_URL_PATTERNS:
            url = template.format(date=token)
            try:
                with self._lock:
                    resp = self._session.get(url, timeout=(8, 12))
            except Exception as exc:
                log.debug("CSV fetch failed", extra={"date": token, "url": url, "err": str(exc)[:200]})
                continue
            if resp.status_code == 404:
                continue
            try:
                resp.raise_for_status()
            except Exception as exc:
                log.debug(
                    "CSV fetch error status",
                    extra={"date": token, "url": url, "status": resp.status_code, "err": str(exc)[:200]},
                )
                continue
            text = resp.text
            if "Index Name" in text:
                return text
        return None


class IndexHistoryStore:
    def __init__(
        self,
        path: Path,
        client: NSEIndexClient,
        specs: Iterable[IndexSpec],
    ) -> None:
        self._path = path
        self._client = client
        self._index_names = tuple(spec.index_name for spec in specs)
        self._lock = threading.Lock()
        self._data: Dict[str, Dict[str, Dict[str, float]]] = self._load()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> Dict[str, Dict[str, Dict[str, float]]]:
        if not self._path.exists():
            return {}
        try:
            with self._path.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
            if isinstance(raw, dict):
                return raw
        except Exception as exc:
            log.warning("Failed to load index history cache", extra={"path": str(self._path), "err": str(exc)[:200]})
        return {}

    def _save_locked(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(self._data, fh, ensure_ascii=False, indent=2)
        tmp.replace(self._path)

    def ensure_date(self, target_date: date) -> bool:
        date_key = target_date.isoformat()
        missing = any(date_key not in (self._data.get(idx_name) or {}) for idx_name in self._index_names)
        if not missing:
            return False

        csv_text = self._client.download_eod_csv(target_date)
        if not csv_text:
            return False

        reader = csv.DictReader(io.StringIO(csv_text))
        updates = 0
        with self._lock:
            for row in reader:
                idx_name = (row.get("Index Name") or "").strip()
                if idx_name not in self._index_names:
                    continue
                close_val = _to_float(row.get("Close Index Value"))
                if close_val is None:
                    continue
                turnover_val = _to_float(row.get("Turnover (Rs. Cr)"))
                entry = self._data.setdefault(idx_name, {})
                record: Dict[str, float] = {"close": close_val}
                if turnover_val is not None:
                    record["turnover_cr"] = turnover_val
                entry[date_key] = record
                updates += 1
            if updates:
                self._save_locked()
        return updates > 0

    def ensure_range(self, start_date: date, end_date: date) -> None:
        cur = start_date
        while cur <= end_date:
            try:
                self.ensure_date(cur)
            except Exception as exc:
                log.debug("ensure_range failed", extra={"date": cur.isoformat(), "err": str(exc)[:200]})
            cur += timedelta(days=1)

    def get_on_or_before(self, index_name: str, target_date: date) -> Optional[Tuple[date, Dict[str, float]]]:
        data = self._data.get(index_name)
        if not data:
            return None
        target_key = target_date.isoformat()
        eligible = [k for k in data.keys() if k <= target_key]
        if not eligible:
            return None
        key = max(eligible)
        return date.fromisoformat(key), data[key]

    def get_nth_prior(self, index_name: str, anchor_date: date, steps: int) -> Optional[Tuple[date, Dict[str, float]]]:
        data = self._data.get(index_name)
        if not data:
            return None
        target_key = anchor_date.isoformat()
        eligible = sorted(k for k in data.keys() if k <= target_key)
        if len(eligible) <= steps:
            return None
        key = eligible[-(steps + 1)]
        return date.fromisoformat(key), data[key]

    def get_recent_entries(
        self, index_name: str, anchor_date: date, limit: int
    ) -> List[Tuple[date, Dict[str, float]]]:
        data = self._data.get(index_name)
        if not data:
            return []
        anchor_key = anchor_date.isoformat()
        eligible = [k for k in data.keys() if k <= anchor_key]
        eligible.sort(reverse=True)
        out: List[Tuple[date, Dict[str, float]]] = []
        for key in eligible:
            out.append((date.fromisoformat(key), data[key]))
            if len(out) >= limit:
                break
        return out


class MomentumHeatmapService:
    def __init__(
        self,
        index_client: Optional[NSEIndexClient] = None,
        history_store: Optional[IndexHistoryStore] = None,
        cache_ttl_seconds: int = CACHE_TTL_SECONDS,
    ) -> None:
        self._client = index_client or NSEIndexClient()
        data_dir = Path(app_config.REPO_ROOT) / "backend" / "data" / "momentum"
        data_dir.mkdir(parents=True, exist_ok=True)
        history_path = data_dir / "nse_index_history.json"
        self._history = history_store or IndexHistoryStore(history_path, self._client, SECTOR_INDICES)
        self._cache_ttl = cache_ttl_seconds
        self._cache_lock = threading.Lock()
        self._cache: Dict[str, Tuple[datetime, MomentumHeatmapResponse]] = {}

    def get_heatmap(
        self,
        as_of: Optional[date] = None,
        include_industries: bool = False,
        include_constituents: bool = False,
    ) -> MomentumHeatmapResponse:
        if include_industries:
            log.debug("MomentumHeatmapService: industries expansion requested but not yet implemented.")
        cache_key = self._cache_key(as_of, include_industries, include_constituents)
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        if as_of:
            raise NotImplementedError("Historical heatmap snapshots are not implemented yet.")

        response = self._build_live_snapshot(
            include_constituents=include_constituents,
            include_industries=include_industries,
        )
        self._store_cache(cache_key, response)
        return response

    def _cache_key(self, as_of: Optional[date], include_industries: bool, include_constituents: bool) -> str:
        return f"{as_of or 'latest'}:{int(include_industries)}:{int(include_constituents)}"

    def _get_cached(self, key: str) -> Optional[MomentumHeatmapResponse]:
        with self._cache_lock:
            entry = self._cache.get(key)
        if not entry:
            return None
        ts, payload = entry
        age = (datetime.now(tz=_UTC) - ts.astimezone(_UTC)).total_seconds()
        if age > self._cache_ttl:
            with self._cache_lock:
                self._cache.pop(key, None)
            return None
        return payload

    def _store_cache(self, key: str, payload: MomentumHeatmapResponse) -> None:
        with self._cache_lock:
            self._cache[key] = (payload.as_of, payload)

    def _build_live_snapshot(
        self,
        include_constituents: bool,
        include_industries: bool,
    ) -> MomentumHeatmapResponse:
        snapshots: List[IndexSnapshot] = []
        notes: List[str] = []

        for spec in SECTOR_INDICES:
            snapshot = self._client.fetch_index_snapshot(spec)
            if snapshot is None:
                notes.append(f"Snapshot unavailable for {spec.index_name}.")
                continue
            snapshots.append(snapshot)

        if not snapshots:
            raise RuntimeError("No NSE sector snapshots available.")

        latest_trade_date = max(s.timestamp.astimezone(_IST).date() for s in snapshots)
        self._history.ensure_range(latest_trade_date - timedelta(days=HISTORY_LOOKBACK_DAYS), latest_trade_date)

        sectors: List[MomentumHeatmapSector] = []
        for snapshot in snapshots:
            try:
                node = self._build_sector_node(snapshot, include_constituents, latest_trade_date)
                sectors.append(node)
            except Exception as exc:
                log.exception("Failed to build sector node", extra={"index": snapshot.spec.index_name})
                notes.append(f"Failed to compute metrics for {snapshot.spec.index_name}: {exc}")

        if not sectors:
            raise RuntimeError("Unable to build momentum heatmap sectors.")

        as_of_dt = max(s.timestamp for s in snapshots).astimezone(_UTC)
        run_id = as_of_dt.strftime("%Y%m%d%H%M%S")
        session = self._infer_session(as_of_dt)
        latency = max(0, int((datetime.now(tz=_UTC) - as_of_dt).total_seconds()))

        metadata = {
            "sectors_requested": len(SECTOR_INDICES),
            "sectors_returned": len(sectors),
            "includes_constituents": include_constituents,
            "includes_industries": include_industries,
        }

        response = MomentumHeatmapResponse(
            as_of=as_of_dt,
            trade_date=latest_trade_date,
            session=session,
            run_id=run_id,
            source="nseindia",
            latency_sec=latency,
            sectors=sectors,
            notes=notes or None,
            metadata=metadata,
        )
        return response

    def _build_sector_node(
        self,
        snapshot: IndexSnapshot,
        include_constituents: bool,
        fallback_trade_date: date,
    ) -> MomentumHeatmapSector:
        target_date = snapshot.timestamp.astimezone(_IST).date()
        anchor = self._history.get_on_or_before(snapshot.spec.index_name, target_date)
        if not anchor:
            anchor = self._history.get_on_or_before(snapshot.spec.index_name, fallback_trade_date)
        note_parts: List[str] = []

        if not anchor:
            note_parts.append("No historical closes available; using intraday movement only.")
            anchor_date = target_date
            anchor_data = {"close": snapshot.last}
        else:
            anchor_date, anchor_data = anchor

        change_1d = snapshot.percent_change
        if change_1d is None and snapshot.previous_close:
            change_1d = ((snapshot.last / snapshot.previous_close) - 1.0) * 100.0
        if change_1d is None:
            change_1d = 0.0

        week_row = self._history.get_nth_prior(snapshot.spec.index_name, anchor_date, WEEK_OFFSET)
        month_row = self._history.get_nth_prior(snapshot.spec.index_name, anchor_date, MONTH_OFFSET)

        change_1w: float = 0.0
        week_available = False
        change_1m: float = 0.0
        month_available = False
        if week_row and (week_row[1].get("close") not in (None, 0)):
            change_1w = ((snapshot.last / week_row[1]["close"]) - 1.0) * 100.0
            week_available = True
        else:
            note_parts.append("Insufficient data for 1W change.")

        if month_row and (month_row[1].get("close") not in (None, 0)):
            change_1m = ((snapshot.last / month_row[1]["close"]) - 1.0) * 100.0
            month_available = True
        else:
            note_parts.append("Insufficient data for 1M change.")

        recent = self._history.get_recent_entries(snapshot.spec.index_name, anchor_date, AVG_TURNOVER_WINDOW)
        avg_turnover = None
        if recent:
            values = [entry[1].get("turnover_cr") for entry in recent if entry[1].get("turnover_cr") not in (None, 0)]
            if values:
                avg_turnover = sum(values) / len(values)

        current_turnover = snapshot.turnover_cr or anchor_data.get("turnover_cr")
        turnover_ratio = _safe_div(current_turnover, avg_turnover) or 0.0

        momentum_score = self._compute_momentum_score(
            change_1d,
            change_1w,
            week_available,
            change_1m,
            month_available,
        )

        advance_decline = None
        if snapshot.advance:
            advance_decline = AdvanceDeclineSummary(
                advancers=snapshot.advance.advancers,
                decliners=snapshot.advance.decliners,
                unchanged=snapshot.advance.unchanged,
            )

        leaders: Optional[List[MomentumHeatmapConstituent]] = None
        laggards: Optional[List[MomentumHeatmapConstituent]] = None
        if include_constituents and snapshot.constituents:
            filtered = [c for c in snapshot.constituents if c.change_pct is not None]
            if filtered:
                filtered.sort(key=lambda c: c.change_pct or 0)
                laggards_raw = filtered[:3]
                leaders_raw = filtered[-3:][::-1]
                leaders = [self._to_constituent_model(c) for c in leaders_raw]
                laggards = [self._to_constituent_model(c) for c in laggards_raw]

        sector = MomentumHeatmapSector(
            name=snapshot.spec.index_name,
            symbol=snapshot.spec.symbol,
            change_1d=round(change_1d, 2),
            change_1w=round(change_1w, 2),
            change_1m=round(change_1m, 2),
            turnover_ratio=round(turnover_ratio, 2),
            last_updated=snapshot.timestamp.astimezone(_UTC),
            momentum_score=momentum_score,
            total_turnover_cr=current_turnover,
            advance_decline=advance_decline,
            industries=[],
            leaders=leaders,
            laggards=laggards,
            note=" ".join(note_parts) if note_parts else None,
        )
        return sector

    def _compute_momentum_score(
        self,
        change_1d: float,
        change_1w: float,
        has_week: bool,
        change_1m: float,
        has_month: bool,
    ) -> Optional[float]:
        components: List[float] = []
        components.append(0.4 * _clamp(change_1d / 5.0, -1.0, 1.0))
        if has_week:
            components.append(0.35 * _clamp(change_1w / 10.0, -1.0, 1.0))
        if has_month:
            components.append(0.25 * _clamp(change_1m / 15.0, -1.0, 1.0))
        if not components:
            return None
        score = sum(components)
        return round(score, 3)

    def _to_constituent_model(self, snap: ConstituentSnapshot) -> MomentumHeatmapConstituent:
        change_1d = snap.change_pct or 0.0
        momentum = _clamp(change_1d / 5.0, -1.0, 1.0)
        turnover_ratio = None
        if snap.turnover_cr and snap.turnover_cr > 0:
            turnover_ratio = snap.turnover_cr / 10.0  # rough normalization
        return MomentumHeatmapConstituent(
            symbol=snap.symbol,
            name=snap.name or snap.symbol,
            last_price=snap.last_price or 0.0,
            change_1d=round(change_1d, 2),
            change_1w=None,
            change_1m=None,
            momentum_score=round(momentum, 3),
            turnover_ratio=turnover_ratio,
            avg_turnover_cr=None,
            weight_pct=snap.weight_pct,
        )

    def _infer_session(self, as_of: datetime) -> str:
        local = as_of.astimezone(_IST)
        if local.weekday() >= 5:
            return "closed"
        start = local.replace(hour=9, minute=15, second=0, microsecond=0)
        end = local.replace(hour=15, minute=30, second=0, microsecond=0)
        post = local.replace(hour=17, minute=0, second=0, microsecond=0)
        if local < start:
            return "pre"
        if local <= end:
            return "cash"
        if local <= post:
            return "post"
        return "closed"


__all__ = [
    "MomentumHeatmapService",
    "NSEIndexClient",
    "IndexHistoryStore",
    "SECTOR_INDICES",
]
