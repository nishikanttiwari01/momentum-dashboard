# app/repos/parquet/news_repo.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Literal, Iterable

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

# ✨ minimal logging (non-invasive)
import logging
import os
import time
import uuid

from app.core.config import load
from app.schemas.generated.models import (
    NewsIngestBatch,
    NewsCard,
    NewsAttributionItem,
    NewsSourceRef,
)

# ──────────────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────────────

log = logging.getLogger(__name__)

def _configure_logging_if_needed(default_level: str = "INFO") -> None:
    root = logging.getLogger()
    if not root.handlers:
        level_name = os.getenv("LOG_LEVEL", default_level).upper()
        level = getattr(logging, level_name, logging.INFO)
        logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
        log.debug("logging.configured", extra={"level": level_name})

def _runid() -> str:
    if not hasattr(_runid, "_id"):
        setattr(_runid, "_id", uuid.uuid4().hex[:12])
    return getattr(_runid, "_id")

def _t0() -> float:
    return time.perf_counter()

def _elapsed_ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000.0, 2)

def _exc(context: str, **extra):
    extra = {"run_id": _runid(), **extra}
    log.exception(context, extra=extra)

_configure_logging_if_needed()

# ──────────────────────────────────────────────────────────────────────────────
# Paths & storage
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class _Paths:
    base_parquet_root: Path
    news_root: Path

_paths: Optional[_Paths] = None


def _configured_base_root() -> Path:
    """
    Use the project-wide parquet_root (e.g. ./backend/parquet) and write news under:
      <parquet_root>/news/partition_date=YYYY-MM-DD/clusters.parquet
    """
    cfg = load()
    base = getattr(cfg, "parquet_root", None) or "./backend/parquet"
    p = Path(base)
    log.debug("news.base_root_resolved", extra={"base": str(p), "run_id": _runid()})
    return p


def ensure_news_storage_ready() -> None:
    global _paths
    base = _configured_base_root()
    news_root = base / "news"
    news_root.mkdir(parents=True, exist_ok=True)
    _paths = _Paths(base_parquet_root=base, news_root=news_root)
    log.debug("news.storage_ready", extra={"root": str(news_root), "run_id": _runid()})


def _partition_dir_from_dt(published: datetime) -> Path:
    """Partition by IST calendar date; values stored as UTC."""
    assert _paths, "ensure_news_storage_ready() must be called first"
    ist = timezone(timedelta(hours=5, minutes=30))
    day = published.astimezone(ist).strftime("%Y-%m-%d")
    p = _paths.news_root / f"partition_date={day}"
    log.debug("news.partition_resolved", extra={
        "published_utc": published.astimezone(timezone.utc).isoformat(),
        "partition": str(p), "run_id": _runid()
    })
    return p


def _parquet_path_for_partition(partition_dir: Path) -> Path:
    p = partition_dir / "clusters.parquet"
    log.debug("news.parquet_path", extra={"path": str(p), "run_id": _runid()})
    return p


# ──────────────────────────────────────────────────────────────────────────────
# Arrow schema
# ──────────────────────────────────────────────────────────────────────────────

_SOURCE_STRUCT = pa.struct([
    ("publisher", pa.string()),
    ("url", pa.string()),
    ("paywalled", pa.bool_()),
])

# ⚠️ Minimal addition: two flat columns (source_primary, source_url)
NEWS_SCHEMA = pa.schema([
    ("cluster_id", pa.string()),
    ("symbol",     pa.string()),
    ("published",  pa.timestamp("ns", tz="UTC")),  # stored as UTC
    ("title",      pa.string()),
    ("event_type", pa.string()),
    ("bullets",    pa.list_(pa.string())),
    ("why",        pa.string()),
    ("sentiment",  pa.string()),
    ("confidence_stars", pa.int32()),
    ("consensus_score",  pa.float32()),
    ("source_count",     pa.int32()),
    ("source_primary",   pa.string()),   # NEW (flat for easy viewing)
    ("source_url",       pa.string()),   # NEW (flat for easy viewing)
    ("sources",          pa.list_(_SOURCE_STRUCT)),
])

log.debug("news.schema_ready", extra={"fields": NEWS_SCHEMA.names, "run_id": _runid()})


def _ingest_item_to_py(obj) -> dict:
    """
    Convert NewsIngestItem (pydantic) to plain types for Arrow.
    Ensure 'published' is tz-aware UTC. Fill flat source_* from first source.
    """
    pub = obj.published
    if pub.tzinfo is None:
        pub = pub.replace(tzinfo=timezone.utc)
    pub_utc = pub.astimezone(timezone.utc)

    src_list = [
        {"publisher": s.publisher, "url": str(s.url), "paywalled": bool(getattr(s, "paywalled", False))}
        for s in (obj.sources or [])
    ]
    first_pub = src_list[0]["publisher"] if src_list else ""
    first_url = src_list[0]["url"] if src_list else ""

    d = {
        "cluster_id": obj.cluster_id,
        "symbol": obj.symbol,
        "published": pub_utc,
        "title": obj.title,
        "event_type": obj.event_type,
        "bullets": list(obj.bullets or []),
        "why": obj.why or "",
        "sentiment": obj.sentiment,
        "confidence_stars": int(obj.confidence_stars or 0),
        "consensus_score": float(obj.consensus_score or 0.0),
        "source_count": int(obj.source_count or 0),
        "source_primary": first_pub,      # NEW
        "source_url": first_url,          # NEW
        "sources": src_list,
    }
    log.debug("news.ingest_item_normalized", extra={"cluster_id": d["cluster_id"], "symbol": d["symbol"], "run_id": _runid()})
    return d


def _table_from_items(items: Iterable[dict]) -> pa.Table:
    t0 = _t0()
    tbl = pa.Table.from_pylist(list(items), schema=NEWS_SCHEMA)
    log.debug("news.arrow_table_built", extra={"rows": tbl.num_rows, "ms": _elapsed_ms(t0), "run_id": _runid()})
    return tbl


# ──────────────────────────────────────────────────────────────────────────────
# Ingest (idempotent upsert by cluster_id per partition)
# ──────────────────────────────────────────────────────────────────────────────

def repo_ingest_batch(batch: NewsIngestBatch) -> None:
    ensure_news_storage_ready()

    log.info("news.ingest_begin", extra={"items": len(batch.items), "run_id": _runid()})

    buckets: dict[Path, list[dict]] = {}
    for it in batch.items:
        pdir = _partition_dir_from_dt(it.published)
        pdir.mkdir(parents=True, exist_ok=True)
        buckets.setdefault(pdir, []).append(_ingest_item_to_py(it))

    for pdir, rows in buckets.items():
        ppath = _parquet_path_for_partition(pdir)
        t0 = _t0()
        if ppath.exists() and ppath.stat().st_size > 0:
            log.debug("news.upsert_read_existing", extra={"path": str(ppath), "run_id": _runid()})
            try:
                existing = pq.read_table(ppath)
            except Exception:
                _exc("news.parquet_read_failed", path=str(ppath))
                raise

            cid_idx: dict[str, int] = {
                existing["cluster_id"][i].as_py(): i
                for i in range(existing.num_rows)
            }

            new_tbl = _table_from_items(rows)

            ex_cols = [existing[name].to_pylist() for name in existing.schema.names]
            name_to_pos = {name: i for i, name in enumerate(existing.schema.names)}

            updated, inserted = 0, 0
            for i in range(new_tbl.num_rows):
                row = {name: new_tbl[name][i].as_py() for name in new_tbl.schema.names}
                cid = row["cluster_id"]
                if cid in cid_idx:
                    pos = cid_idx[cid]
                    for name, val in row.items():
                        ex_cols[name_to_pos[name]][pos] = val
                    updated += 1
                else:
                    for name, val in row.items():
                        ex_cols[name_to_pos[name]].append(val)
                    inserted += 1

            merged = pa.Table.from_arrays(ex_cols, schema=existing.schema)
            try:
                pq.write_table(
                    merged, ppath,
                    compression="zstd",
                    use_dictionary=True,
                    write_statistics=True,
                )
            except Exception:
                _exc("news.parquet_write_failed", path=str(ppath))
                raise
            log.info("news.upsert_done", extra={
                "path": str(ppath), "existing_rows": existing.num_rows,
                "updated": updated, "inserted": inserted, "ms": _elapsed_ms(t0),
                "run_id": _runid(),
            })
        else:
            log.debug("news.new_partition_write", extra={"path": str(ppath), "rows": len(rows), "run_id": _runid()})
            tbl = _table_from_items(rows)
            try:
                pq.write_table(
                    tbl, ppath,
                    compression="zstd",
                    use_dictionary=True,
                    write_statistics=True,
                )
            except Exception:
                _exc("news.parquet_write_failed", path=str(ppath))
                raise
            log.info("news.partition_created", extra={"path": str(ppath), "rows": tbl.num_rows, "ms": _elapsed_ms(t0), "run_id": _runid()})

    log.info("news.ingest_complete", extra={"partitions": len(buckets), "run_id": _runid()})


# ──────────────────────────────────────────────────────────────────────────────
# Query via DuckDB over Parquet
# ──────────────────────────────────────────────────────────────────────────────

def _parquet_glob_between(from_dt: datetime, to_dt: datetime) -> str:
    assert _paths
    ist = timezone(timedelta(hours=5, minutes=30))
    start_day = from_dt.astimezone(ist).date()
    end_day = to_dt.astimezone(ist).date()

    parts = []
    day = start_day
    while day <= end_day:
        parts.append(f"partition_date={day.isoformat()}/clusters.parquet")
        day = day + timedelta(days=1)

    if not parts:
        g = str(_paths.news_root / "partition_date=*/clusters.parquet")
        log.debug("news.glob_auto_all", extra={"glob": g, "run_id": _runid()})
        return g
    if len(parts) == 1:
        g = str(_paths.news_root / parts[0])
        log.debug("news.glob_single", extra={"glob": g, "run_id": _runid()})
        return g
    brace = ",".join(parts)
    g = str(_paths.news_root / f"{{{brace}}}")
    log.debug("news.glob_multi", extra={"glob": g, "days": len(parts), "run_id": _runid()})
    return g


def repo_list_news(
    symbol: str,
    from_dt: datetime,
    to_dt: datetime,
    page: int,
    per_page: int,
    min_confidence: Optional[int],
    event_filter: Optional[list[str]],
    sort: Literal["impact_desc", "published_desc", "confirmed_desc"],
) -> tuple[list[NewsCard], Optional[int]]:
    """Read Parquet via DuckDB and return paginated NewsCard rows for a symbol."""
    ensure_news_storage_ready()

    f_utc = (from_dt.replace(tzinfo=timezone.utc)
             if from_dt.tzinfo is None else from_dt.astimezone(timezone.utc))
    t_utc = (to_dt.replace(tzinfo=timezone.utc)
             if to_dt.tzinfo is None else to_dt.astimezone(timezone.utc))

    glob = _parquet_glob_between(from_dt, to_dt)
    log.info("news.query_begin", extra={
        "symbol": symbol, "from_utc": f_utc.isoformat(), "to_utc": t_utc.isoformat(),
        "page": page, "per_page": per_page, "min_conf": min_confidence,
        "events": (event_filter or []), "sort": sort, "glob": glob, "run_id": _runid(),
    })
    t0 = _t0()
    con = duckdb.connect(database=":memory:")
    try:
        where = ["symbol = ?", "published BETWEEN ? AND ?"]
        params: list = [symbol, f_utc, t_utc]

        if min_confidence:
            where.append("confidence_stars >= ?")
            params.append(int(min_confidence))

        if event_filter:
            placeholders = ",".join("?" for _ in event_filter)
            where.append(f"event_type IN ({placeholders})")
            params.extend(event_filter)

        if sort == "published_desc":
            order = "published DESC"
        elif sort == "confirmed_desc":
            order = "source_count DESC, confidence_stars DESC, published DESC"
        else:
            order = "((coalesce(consensus_score,0)) + 0.15*confidence_stars + 0.05*source_count) DESC, published DESC"

        q_base = f"""
          FROM read_parquet('{glob}')
          WHERE {" AND ".join(where)}
        """

        total = con.execute(f"SELECT COUNT(*) {q_base}", params).fetchone()[0]

        offset = max(0, (page - 1) * per_page)
        q = f"""
          SELECT cluster_id, symbol, published, title, event_type, bullets, why,
                 sentiment, confidence_stars, consensus_score, source_count,source_primary, source_url, sources      
          {q_base}
          ORDER BY {order}
          LIMIT ? OFFSET ?
        """
        rows = con.execute(q, params + [per_page, offset]).fetchall()
        log.info("news.query_rows_fetched", extra={
            "total": int(total), "returned": len(rows), "offset": offset,
            "ms": _elapsed_ms(t0), "run_id": _runid(),
        })
    except Exception:
        _exc("news.query_failed", symbol=symbol, glob=glob)
        raise
    finally:
        try:
            con.close()
        except Exception:
            log.debug("duckdb.close_failed", extra={"run_id": _runid()})

    items: list[NewsCard] = []
    for (cluster_id, _symbol, published, title, event_type, bullets, why,
         sentiment, confidence_stars, consensus_score, source_count, sources,source_primary,source_url) in rows:

        pub_dt: datetime = published  # duckdb returns tz-aware UTC
        src_refs: list[NewsSourceRef] = []
        if sources:
            for s in sources:
                if isinstance(s, dict):
                    src_refs.append(
                        NewsSourceRef(
                            publisher=s.get("publisher", ""),
                            url=str(s.get("url", "")),
                            paywalled=bool(s.get("paywalled", False)),
                        )
                    )
                else:
                    pub, url, pay = s
                    src_refs.append(NewsSourceRef(publisher=pub, url=url, paywalled=bool(pay)))

        items.append(
            NewsCard(
                cluster_id=cluster_id,
                published=pub_dt,
                title=title,
                event_type=event_type,
                bullets=list(bullets or []),
                why=why or "",
                sentiment=sentiment,
                confidence_stars=int(confidence_stars or 0),
                consensus_score=float(consensus_score or 0.0),
                source_count=int(source_count or 0),
                sources=src_refs,
                source_primary=source_primary,
                source_url=source_url,
                impact_score=None,
                correlation_note=None,
            )
        )

    next_page = page + 1 if (offset + per_page) < total else None
    log.info("news.query_complete", extra={
        "symbol": symbol, "items": len(items), "next_page": next_page,
        "window_min": round((t_utc - f_utc).total_seconds() / 60.0, 1),
        "run_id": _runid(),
    })
    return items, next_page


# ──────────────────────────────────────────────────────────────────────────────
# Attribution (impact scoring)
# ──────────────────────────────────────────────────────────────────────────────

def _recency_decay(minutes: float) -> float:
    cfg = load().news.consensus if (load().news and getattr(load().news, "consensus", None)) else {}
    buckets = (cfg.get("recency_decay") or {}).get("buckets") or [
        {"max_min": 30, "factor": 1.00},
        {"max_min": 90, "factor": 0.80},
        {"max_min": 240, "factor": 0.50},
        {"max_min": 1440, "factor": 0.30},
    ]
    for b in buckets:
        if minutes <= float(b["max_min"]):
            return float(b["factor"])
    return float(buckets[-1]["factor"])


def _event_boost(event_type: str) -> float:
    boosts = (load().news.events or {}).get("boosts") if (load().news and getattr(load().news, "events", None)) else {}
    return float((boosts or {}).get(event_type, (boosts or {}).get("other", 1.0))) or 1.0


def repo_attribute_move(
    symbol: str,
    at: datetime,
    lookback_min: int,
    min_confidence: Optional[int],
) -> list[NewsAttributionItem]:
    """
    Attribute a price move at 'at' to recent news for 'symbol'.
    Returns the top 3 by computed impact.
    """
    t0 = _t0()
    from_dt = at - timedelta(minutes=lookback_min)
    log.info("news.attrib_begin", extra={
        "symbol": symbol, "at": at.astimezone(timezone.utc).isoformat(),
        "lookback_min": lookback_min, "min_conf": min_confidence, "run_id": _runid(),
    })
    candidates, _ = repo_list_news(
        symbol=symbol,
        from_dt=from_dt,
        to_dt=at,
        page=1,
        per_page=1000,
        min_confidence=min_confidence,
        event_filter=None,
        sort="published_desc",
    )

    out: list[NewsAttributionItem] = []
    for c in candidates:
        minutes_ago = max(0.0, (at - c.published).total_seconds() / 60.0)
        rec = _recency_decay(minutes_ago)
        ev = _event_boost(c.event_type)

        impact_raw = (
            (c.consensus_score or 0.0)
            + 0.18 * (c.confidence_stars or 0)
            + 0.06 * (c.source_count or 0)
        ) * rec * ev

        impact = max(0.0, min(1.0, impact_raw))

        thr = {}
        if load().news and getattr(load().news, "attribution", None):
            thr = load().news.attribution.get("thresholds", {}) or {}
        likely_thr = float(thr.get("likely", 0.65))
        possible_thr = float(thr.get("possible", 0.45))
        if impact >= likely_thr:
            decision: Literal["likely","possible","none"] = "likely"
        elif impact >= possible_thr:
            decision = "possible"
        else:
            decision = "none"

        if minutes_ago <= 5:
            note = "Appeared within 5m of the move"
        elif minutes_ago <= 30:
            note = f"Appeared {int(minutes_ago)}m before move"
        else:
            note = f"Appeared {int(minutes_ago)}m before move (older)"

        out.append(
            NewsAttributionItem(
                cluster_id=c.cluster_id,
                decision=decision,  # type: ignore
                impact_score=impact,
                card=c.copy(update={"impact_score": impact, "correlation_note": note}),
            )
        )

    out.sort(key=lambda x: (x.impact_score or 0.0), reverse=True)
    result = out[:3]
    log.info("news.attrib_complete", extra={
        "symbol": symbol, "candidates": len(candidates), "top": len(result),
        "ms": _elapsed_ms(t0), "run_id": _runid(),
    })
    return result
