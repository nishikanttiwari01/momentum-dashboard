# app/repos/parquet/news_repo.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Literal, Iterable

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from app.core.config import load
from app.schemas.generated.models import (
    NewsIngestBatch,
    NewsCard,
    NewsAttributionItem,
    NewsSourceRef,
)

# ──────────────────────────────────────────────────────────────────────────────
# Paths & storage lifecycle (uses existing global parquet_root)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class _Paths:
    base_parquet_root: Path       # e.g. ./backend/parquet (your existing root)
    news_root: Path               # <base>/news

_paths: Optional[_Paths] = None


def _configured_base_root() -> Path:
    """
    Resolve your existing Parquet root.

    We intentionally DO NOT introduce a second root. This respects your
    project-wide setting (e.g. ./backend/parquet) and writes news under:
        <parquet_root>/news/partition_date=YYYY-MM-DD/clusters.parquet
    """
    cfg = load()
    # Prefer the same config key you use elsewhere (commonly 'parquet_root').
    # Fallback to ./backend/parquet to match your existing repo convention.
    base = getattr(cfg, "parquet_root", None) or "./backend/parquet"
    return Path(base)


def ensure_news_storage_ready() -> None:
    """Ensure <parquet_root>/news exists."""
    global _paths
    base = _configured_base_root()
    news_root = base / "news"
    news_root.mkdir(parents=True, exist_ok=True)
    _paths = _Paths(base_parquet_root=base, news_root=news_root)


def _partition_dir_from_dt(published: datetime) -> Path:
    """
    Partition by India date (IST day boundary). We store data in UTC but the
    folder partition reflects IST to align with Indian market/news days.
    """
    assert _paths, "ensure_news_storage_ready() must be called first"
    # IST is UTC+5:30
    ist = timezone(timedelta(hours=5, minutes=30))
    day = published.astimezone(ist).strftime("%Y-%m-%d")
    return _paths.news_root / f"partition_date={day}"


def _parquet_path_for_partition(partition_dir: Path) -> Path:
    # One file per day keeps it simple and fast to scan
    return partition_dir / "clusters.parquet"


# ──────────────────────────────────────────────────────────────────────────────
# Arrow schemas & conversion
# ──────────────────────────────────────────────────────────────────────────────

_SOURCE_STRUCT = pa.struct([
    ("publisher", pa.string()),
    ("url", pa.string()),
    ("paywalled", pa.bool_()),
])

NEWS_SCHEMA = pa.schema([
    ("cluster_id", pa.string()),
    ("symbol",     pa.string()),
    ("published",  pa.timestamp("ns", tz="UTC")),  # store as UTC
    ("title",      pa.string()),
    ("event_type", pa.string()),
    ("bullets",    pa.list_(pa.string())),
    ("why",        pa.string()),
    ("sentiment",  pa.string()),
    ("confidence_stars", pa.int32()),
    ("consensus_score",  pa.float32()),
    ("source_count",     pa.int32()),
    ("sources",          pa.list_(_SOURCE_STRUCT)),
])


def _ingest_item_to_py(obj) -> dict:
    """
    Convert a NewsIngestItem (pydantic) into plain Python types for Arrow.
    Ensure 'published' is timezone-aware UTC.
    """
    pub = obj.published
    if pub.tzinfo is None:
        pub = pub.replace(tzinfo=timezone.utc)
    pub_utc = pub.astimezone(timezone.utc)
    return {
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
        "sources": [
            {"publisher": s.publisher, "url": str(s.url), "paywalled": bool(getattr(s, "paywalled", False))}
            for s in (obj.sources or [])
        ],
    }


def _table_from_items(items: Iterable[dict]) -> pa.Table:
    return pa.Table.from_pylist(list(items), schema=NEWS_SCHEMA)


# ──────────────────────────────────────────────────────────────────────────────
# Ingest (idempotent upsert by cluster_id within the partition)
# ──────────────────────────────────────────────────────────────────────────────

def repo_ingest_batch(batch: NewsIngestBatch) -> None:
    """
    Upsert each item into its IST-dated partition. If the partition file exists,
    we update rows by cluster_id; otherwise we create the file.
    """
    ensure_news_storage_ready()

    # Group incoming items by their partition dir
    buckets: dict[Path, list[dict]] = {}
    for it in batch.items:
        pdir = _partition_dir_from_dt(it.published)
        pdir.mkdir(parents=True, exist_ok=True)
        buckets.setdefault(pdir, []).append(_ingest_item_to_py(it))

    # Upsert per partition
    for pdir, rows in buckets.items():
        ppath = _parquet_path_for_partition(pdir)
        if ppath.exists() and ppath.stat().st_size > 0:
            existing = pq.read_table(ppath)

            # Map cluster_id -> row index
            cid_idx: dict[str, int] = {
                existing["cluster_id"][i].as_py(): i
                for i in range(existing.num_rows)
            }

            # Incoming as Arrow table
            new_tbl = _table_from_items(rows)

            # Mutable lists of existing columns
            ex_cols = [existing[name].to_pylist() for name in existing.schema.names]
            name_to_pos = {name: i for i, name in enumerate(existing.schema.names)}

            # Upsert/append
            for i in range(new_tbl.num_rows):
                row = {name: new_tbl[name][i].as_py() for name in new_tbl.schema.names}
                cid = row["cluster_id"]
                if cid in cid_idx:
                    pos = cid_idx[cid]
                    for name, val in row.items():
                        ex_cols[name_to_pos[name]][pos] = val
                else:
                    for name, val in row.items():
                        ex_cols[name_to_pos[name]].append(val)

            merged = pa.Table.from_arrays(ex_cols, schema=existing.schema)
            pq.write_table(
                merged, ppath,
                compression="zstd",
                use_dictionary=True,
                write_statistics=True,
            )
        else:
            tbl = _table_from_items(rows)
            pq.write_table(
                tbl, ppath,
                compression="zstd",
                use_dictionary=True,
                write_statistics=True,
            )


# ──────────────────────────────────────────────────────────────────────────────
# Query via DuckDB over Parquet
# ──────────────────────────────────────────────────────────────────────────────

def _parquet_glob_between(from_dt: datetime, to_dt: datetime) -> str:
    """
    Build a DuckDB glob covering all IST-partitioned days intersecting [from..to].
    """
    assert _paths
    ist = timezone(timedelta(hours=5, minutes=30))
    start_day = from_dt.astimezone(ist).date()
    end_day = to_dt.astimezone(ist).date()

    parts = []
    day = start_day
    while day <= end_day:
        parts.append(f"partition_date={day.isoformat()}/clusters.parquet")
        day = day + timedelta(days=1)

    # 'root/{a,b,c}' form for DuckDB
    if not parts:
        return str(_paths.news_root / "partition_date=*/clusters.parquet")
    if len(parts) == 1:
        return str(_paths.news_root / parts[0])
    brace = ",".join(parts)
    return str(_paths.news_root / f"{{{brace}}}")


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
    """
    Read Parquet via DuckDB and return paginated NewsCard rows for a symbol.
    """
    ensure_news_storage_ready()

    # Normalize times to UTC for filtering (we stored 'published' as UTC)
    f_utc = (from_dt.replace(tzinfo=timezone.utc)
             if from_dt.tzinfo is None else from_dt.astimezone(timezone.utc))
    t_utc = (to_dt.replace(tzinfo=timezone.utc)
             if to_dt.tzinfo is None else to_dt.astimezone(timezone.utc))

    glob = _parquet_glob_between(from_dt, to_dt)
    con = duckdb.connect(database=":memory:")
    # (No extensions required; defaults are fine.)

    where = ["symbol = ?", "published BETWEEN ? AND ?"]
    params: list = [symbol, f_utc, t_utc]

    if min_confidence:
        where.append("confidence_stars >= ?")
        params.append(int(min_confidence))

    if event_filter:
        placeholders = ",".join("?" for _ in event_filter)
        where.append(f"event_type IN ({placeholders})")
        params.extend(event_filter)

    # Sorting
    if sort == "published_desc":
        order = "published DESC"
    elif sort == "confirmed_desc":
        order = "source_count DESC, confidence_stars DESC, published DESC"
    else:
        # impact_desc proxy using consensus + stars + sources + recency(neutralized by published DESC)
        order = "((coalesce(consensus_score,0)) + 0.15*confidence_stars + 0.05*source_count) DESC, published DESC"

    q_base = f"""
      FROM read_parquet('{glob}')
      WHERE {" AND ".join(where)}
    """

    total = con.execute(f"SELECT COUNT(*) {q_base}", params).fetchone()[0]

    offset = max(0, (page - 1) * per_page)
    q = f"""
      SELECT cluster_id, symbol, published, title, event_type, bullets, why,
             sentiment, confidence_stars, consensus_score, source_count, sources
      {q_base}
      ORDER BY {order}
      LIMIT ? OFFSET ?
    """
    rows = con.execute(q, params + [per_page, offset]).fetchall()

    items: list[NewsCard] = []
    for (cluster_id, _symbol, published, title, event_type, bullets, why,
         sentiment, confidence_stars, consensus_score, source_count, sources) in rows:

        pub_dt: datetime = published  # duckdb returns tz-aware UTC

        # Convert nested sources
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
                impact_score=None,
                correlation_note=None,
            )
        )

    next_page = page + 1 if (offset + per_page) < total else None
    return items, next_page


# ──────────────────────────────────────────────────────────────────────────────
# Attribution (impact scoring with config boosts & recency)
# ──────────────────────────────────────────────────────────────────────────────

def _recency_decay(minutes: float) -> float:
    """
    Recency decay buckets from config:
      news.consensus.recency_decay.buckets:
        - { max_min: 30,   factor: 1.00 }
        - { max_min: 90,   factor: 0.80 }
        - { max_min: 240,  factor: 0.50 }
        - { max_min: 1440, factor: 0.30 }
    """
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
    Attribute a price move at 'at' (UTC or tz-aware) to recent news for 'symbol'.
    Returns the top 3 by computed impact.
    """
    # Candidates window
    from_dt = at - timedelta(minutes=lookback_min)
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

        # Impact: consensus + stars + sources, modulated by recency & event boost
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
        decision: Literal["likely", "possible", "none"]
        if impact >= likely_thr:
            decision = "likely"
        elif impact >= possible_thr:
            decision = "possible"
        else:
            decision = "none"

        # Correlation note
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
    return out[:3]
