# backend/app/pipeline/news_provider.py
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import sys
import time
import requests
import feedparser
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import quote_plus

# ✨ added
import logging
import uuid

from app.core.config import load as load_settings
from app.schemas.generated.models import (
    NewsIngestBatch,
    NewsIngestItem,
    NewsSourceRef,
)

# ──────────────────────────────────────────────────────────────────────────────
# Logging bootstrap (non-invasive)
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

def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000.0, 2)

def _exc(context: str, **extra):
    extra = {"run_id": _runid(), **extra}
    log.exception(context, extra=extra)

# Ensure we have logging when invoked as a standalone CLI
_configure_logging_if_needed()

# ──────────────────────────────────────────────────────────────────────────────
# Utils
# ──────────────────────────────────────────────────────────────────────────────
# --- robust kv logging helpers (no `extra=`, fixed to use logging module) ---
import logging as _logging

def _kv_str(**kv):
    return " ".join(f"{k}={repr(v)}" for k, v in kv.items() if v is not None)

def _pick_logger():
    # Prefer the module's `log` if it exists; else use module logger
    lg = globals().get("log")
    if not isinstance(lg, _logging.Logger):
        lg = _logging.getLogger(__name__)
    # Ensure there is at least one handler; otherwise attach console handler
    if not lg.handlers:
        h = _logging.StreamHandler()
        fmt = _logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        h.setFormatter(fmt)
        lg.addHandler(h)
    # Ensure level allows INFO unless user set it lower
    if lg.level == _logging.NOTSET or lg.level > _logging.INFO:
        lg.setLevel(_logging.INFO)
    # Let it bubble to root unless your app disables it
    lg.propagate = True
    return lg

def _log_kv(level: int, msg: str, **kv) -> None:
    lg = _pick_logger()
    if lg.isEnabledFor(level):
        lg.log(level, f"{msg}" + ("" if not kv else f" | {_kv_str(**kv)}"))

def _debug(msg: str, **kv): _log_kv(_logging.DEBUG, msg, **kv)
def _info(msg: str,  **kv): _log_kv(_logging.INFO,  msg, **kv)
def _warn(msg: str,  **kv): _log_kv(_logging.WARNING, msg, **kv)
def _error(msg: str, **kv): _log_kv(_logging.ERROR, msg, **kv)

def _stderr(msg: str) -> None:
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _parse_since_minutes(since: str | int) -> int:
    if isinstance(since, int):
        return max(1, since)
    s = str(since).strip().lower()
    if s.endswith("m"):  # "10m"
        return max(1, int(float(s[:-1])))
    if s.endswith("h"):  # "2h"
        return max(1, int(float(s[:-1]) * 60))
    if s.endswith("d"):  # "1d"
        return max(1, int(float(s[:-1]) * 1440))
    return max(1, int(float(s)))

def _ts_aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

def _norm_text(x: str) -> str:
    x = html.unescape(x or "")
    x = re.sub(r"\s+", " ", x).strip()
    return x

def _tokenize_title(t: str) -> Set[str]:
    t = t.lower()
    t = re.sub(r"[^a-z0-9\s%&\-\.]", " ", t)
    toks = set(w for w in t.split() if len(w) > 1)
    return toks

def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    i = len(a & b)
    u = len(a | b)
    return i / max(1, u)

def _hash_cluster(symbol: str, title: str, pub: datetime, primary_source: str) -> str:
    key = f"{symbol}|{title[:140]}|{_ts_aware(pub).isoformat()}|{primary_source}"
    return "clu_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]

# ──────────────────────────────────────────────────────────────────────────────
# Config-driven source weighting
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class SourceWeight:
    publisher: str
    weight: float

def _build_source_weights() -> Dict[str, float]:
    s = load_settings()
    weights: Dict[str, float] = {}
    for o in (s.news.sources.get("official") or []):
        nm = (o.get("name") or "").strip()
        if nm:
            weights[nm.lower()] = float(o.get("weight", 1.0))
    for m in (s.news.sources.get("media_sites") or []):
        dom = (m.get("domain") or "").strip().lower()
        if dom:
            weights[dom] = float(m.get("weight", 0.9))
    # sensible defaults
    if "reuters.com" not in weights:
        weights["reuters.com"] = 0.95
    log.debug("news.weights_ready", extra={"count": len(weights), "run_id": _runid()})
    return weights

# ──────────────────────────────────────────────────────────────────────────────
# Aliases & symbol master
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class SymbolMap:
    # symbol -> set of matchable phrases
    match: Dict[str, Set[str]]

def _load_aliases() -> SymbolMap:
    cfg = load_settings().news.mapping or {}
    alias_csv = cfg.get("aliases_csv")
    master_csv = cfg.get("nse_master_csv")
    match: Dict[str, Set[str]] = {}

    def add(sym: str, phrase: str):
        sym = sym.strip()
        phrase = phrase.strip()
        if not sym or not phrase:
            return
        match.setdefault(sym, set()).add(phrase.lower())

    # aliases.csv: symbol,alias
    if alias_csv and Path(alias_csv).exists():
        t0 = _t0()
        with open(alias_csv, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                add(row.get("symbol", ""), row.get("alias", ""))
        log.info("news.aliases_loaded", extra={"path": alias_csv, "symbols": len(match), "ms": _ms(t0), "run_id": _runid()})

    # nse_master.csv: symbol,isin,company_name,sector
    if master_csv and Path(master_csv).exists():
        t0 = _t0()
        with open(master_csv, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                add(row.get("symbol", ""), row.get("company_name", ""))
        log.info("news.master_loaded", extra={"path": master_csv, "symbols": len(match), "ms": _ms(t0), "run_id": _runid()})

    # fallback: symbol itself
    for sym in list(match.keys()):
        add(sym, sym.split(".")[0])  # e.g., RELIANCE from RELIANCE.NS

    log.debug("news.alias_map_ready", extra={"symbols": len(match), "run_id": _runid()})
    return SymbolMap(match=match)

def _headline_matches_symbol(headline: str, sym: str, smap: SymbolMap) -> bool:
    hay = headline.lower()
    for phrase in smap.match.get(sym, set()):
        if phrase and phrase in hay:
            return True
    # allow strict symbol token match if short
    base = sym.split(".")[0].lower()
    if base and base in hay:
        return True
    return False

# ──────────────────────────────────────────────────────────────────────────────
# Fetchers (RSS + Google News RSS)
# ──────────────────────────────────────────────────────────────────────────────

def _fetch_rss(url: str, timeout: int = 15) -> List[dict]:
    """
    Robust RSS fetcher:
      - Uses requests with connect/read timeouts and retries
      - Falls back cleanly on failures
      - Parses bytes via feedparser to avoid internal network calls
    """
    t0 = _t0()
    out: List[dict] = []

    # Split total timeout into connect/read; keep conservative defaults
    CONNECT_TO = min(8, timeout)          # seconds
    READ_TO    = max(4, min(12, timeout)) # seconds
    RETRIES    = 2
    UA = os.getenv("NEWS_RSS_UA", "Mozilla/5.0 (compatible; MomentumSuite/1.0; +https://localhost)")

    _info("rss.fetch_start", url=url, connect_to=CONNECT_TO, read_to=READ_TO, retries=RETRIES)
    last_err = None

    for attempt in range(1, RETRIES + 2):  # e.g., 1..3 total tries when RETRIES=2
        try:
            # Use a HEAD ping to fail fast on dead hosts (optional)
            try:
                requests.head(url, timeout=(CONNECT_TO, 3), headers={"User-Agent": UA})
            except Exception:
                pass  # non-fatal; move on to GET

            resp = requests.get(url, timeout=(CONNECT_TO, READ_TO), headers={"User-Agent": UA})
            resp.raise_for_status()

            # Parse the bytes we fetched so feedparser doesn't make its own network calls
            parsed = feedparser.parse(resp.content)

            for e in parsed.entries:
                title = _norm_text(e.get("title", ""))
                link = e.get("link") or ""
                published = None
                for key in ("published_parsed", "updated_parsed"):
                    if e.get(key):
                        published = datetime(*e[key][:6], tzinfo=timezone.utc)
                        break
                out.append({"title": title, "url": link, "published": published})

            _info("rss.fetch_ok", url=url, items=len(out), ms=_ms(t0), attempt=attempt)
            return out
        except Exception as e:
            last_err = e
            _warn("rss.fetch_attempt_failed", url=url, attempt=attempt, err=str(e)[:180])
            # small backoff before next retry
            try:
                time.sleep(0.6 * attempt)
            except Exception:
                pass

    # All attempts failed
    _error("rss.fetch_failed", url=url, err=str(last_err)[:300], ms=_ms(t0))
    return out  # empty list on failure (callers already handle)


def _google_news_rss(site: str, query: str) -> str:
    # Example: https://news.google.com/rss/search?q=site:moneycontrol.com+(INFY)+when:12h&hl=en-IN&gl=IN&ceid=IN:en
    base = "https://news.google.com/rss/search?q="
    q = f"site:{site} ({quote_plus(query)}) when:24h"
    return f"{base}{q}&hl=en-IN&gl=IN&ceid=IN:en"

def _fetch_media_for_symbol(sym: str, aliases: List[str], sites: List[str]) -> List[dict]:
    items: List[dict] = []
    query = " OR ".join([sym.split(".")[0]] + aliases[:2])  # keep short to reduce noise
    for site in sites:
        url = _google_news_rss(site, query)
        items.extend(_fetch_rss(url))
    log.debug("media.symbol_fetched", extra={"symbol": sym, "sites": len(sites), "items": len(items), "run_id": _runid()})
    return items

# ──────────────────────────────────────────────────────────────────────────────
# Summarizer (Ollama optional)
# ──────────────────────────────────────────────────────────────────────────────

def _ollama_generate_bullets_why(text: str, model: str = "llama3", timeout: int = 20) -> Tuple[List[str], str, str, str]:
    """
    Returns (bullets, why, event_type, sentiment). If Ollama unavailable, returns a heuristic fallback.
    """
    host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    url = f"{host.rstrip('/')}/api/generate"
    prompt = (
        "Summarize the following finance news into:\n"
        "1) 2-5 factual bullet points (numbers preserved),\n"
        "2) one brief 'why it matters' line,\n"
        "3) event_type from {results, order_win, pledge, rating_change, regulatory, court, mna, guidance, mgmt_change, macro, other},\n"
        "4) sentiment from {positive, negative, mixed, neutral}.\n"
        "Return strict JSON with keys bullets, why, event_type, sentiment.\n\n"
        f"TEXT:\n{text}\n"
    )
    try:
        t0 = _t0()
        payload = {"model": model, "prompt": prompt, "stream": False, "options": {"num_predict": 256}}
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        content = resp.json().get("response", "").strip()
        # Extract JSON (model may return extra)
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("No JSON found in LLM response")
        data = json.loads(content[start : end + 1])
        bullets = [str(b).strip() for b in data.get("bullets", [])][:5] or []
        why = str(data.get("why", "")).strip()
        event_type = str(data.get("event_type", "other")).strip()
        sentiment = str(data.get("sentiment", "neutral")).strip()
        log.debug("ollama.ok", extra={"model": model, "bullets": len(bullets), "ms": _ms(t0), "run_id": _runid()})
        return bullets, why, event_type, sentiment
    except Exception as e:
        log.info("ollama.fallback_used", extra={"reason": str(e)[:120], "model": model, "run_id": _runid()})
        # Fallback heuristic: title-based bullet and neutral sentiment
        text = _norm_text(text)
        head = text.split(".")[0][:140]
        return [head], "Potentially price relevant; confirm with sources.", "other", "neutral"

# ──────────────────────────────────────────────────────────────────────────────
# Core: build clusters per symbol
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class RawHit:
    symbol: str
    title: str
    url: str
    publisher: str
    published: Optional[datetime]

def _publisher_from_url(url: str) -> str:
    try:
        host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0].lower()
        return host
    except Exception:
        return "unknown"

def _within_window(pub: Optional[datetime], since_minutes: int, anchor: datetime) -> bool:
    if pub is None:
        return True  # keep if time unknown (we’ll let recency weighting handle it)
    return anchor - timedelta(minutes=since_minutes) <= pub <= anchor + timedelta(minutes=5)

def _collect_hits(symbols: List[str], since_minutes: int, anchor: datetime, smap: SymbolMap) -> List[RawHit]:
    s = load_settings()
    t0 = _t0()
    hits: List[RawHit] = []

    # Official feeds (not symbol-specific, filter by aliases)
    official = s.news.sources.get("official") or []
    # (existing) keep as-is:
    log.info("collect.official_begin", extra={"feeds": len(official), "run_id": _runid()})
    # (new) var-arg style:
    _info("collect.official_begin+", feeds=len(official), since_min=since_minutes, anchor=anchor.isoformat(), symbols=len(symbols))

    for src in official:
        url = src.get("url")
        if not url:
            _debug("collect.official.skip_no_url", src=src)
            continue

        feed_seen = 0
        feed_skipped_window = 0
        feed_matched = 0
        _debug("collect.official.feed_start", url=url)

        for ent in _fetch_rss(url):
            title = ent["title"]
            pub = ent["published"]
            feed_seen += 1

            if not _within_window(pub, since_minutes, anchor):
                feed_skipped_window += 1
                _debug(
                    "collect.official.entry_skipped_window",
                    url=url,
                    published=(pub.isoformat() if pub else None),
                    title_preview=(title[:120] if title else None),
                )
                continue

            pubr = src.get("name") or _publisher_from_url(url)
            link = ent["url"]
            _debug("collect.official.entry_in_window", publisher=pubr, link=link)

            # Map to symbols by alias match
            for sym in symbols:
                matched = _headline_matches_symbol(title, sym, smap)
                _debug(
                    "collect.official.entry_match_check",
                    symbol=sym,
                    matched=matched,
                    title_preview=(title[:120] if title else None),
                )
                if matched:
                    hits.append(RawHit(sym, title, link, pubr, pub))
                    feed_matched += 1
                    _debug(
                        "collect.official.entry_matched",
                        symbol=sym,
                        publisher=pubr,
                        published=(pub.isoformat() if pub else None),
                    )

        _info(
            "collect.official.feed_complete",
            url=url,
            seen=feed_seen,
            skipped_window=feed_skipped_window,
            matched=feed_matched,
        )

    # (existing) keep as-is:
    log.info("collect.official_done", extra={"hits": len(hits), "ms": _ms(t0), "run_id": _runid()})
    # (new)
    _info("collect.official_done+", hits=len(hits), ms=_ms(t0))

    # Media via Google News (site-filtered)
    gcfg = s.news.sources.get("google_news") or s.news.get("google_news") or {}
    if gcfg and (gcfg.get("enabled", True)):
        sites = list(gcfg.get("sites") or [])
        # (existing) keep:
        log.info("collect.media_begin", extra={"sites": len(sites), "symbols": len(symbols), "run_id": _runid()})
        # (new)
        _info("collect.media_begin+", sites=len(sites), symbols=len(symbols))

        t1 = _t0()
        # build quick alias map list for speed
        alias_map: Dict[str, List[str]] = {sym: list(smap.match.get(sym, set())) for sym in symbols}
        _debug("collect.media.alias_map_ready", entries=sum(len(v) for v in alias_map.values()))

        for sym in symbols:
            sym_seen = 0
            sym_skipped = 0
            sym_matched = 0
            _debug("collect.media.symbol_start", symbol=sym, aliases=len(alias_map.get(sym, [])), sites=len(sites))
            try:
                items = _fetch_media_for_symbol(sym, alias_map.get(sym, []), sites)
                _debug("collect.media.symbol_fetched", symbol=sym, items=len(items))
            except Exception as e:
                _stderr(f"[warn] media fetch failed for {sym}: {e}")
                _exc("collect.media_fetch_failed", symbol=sym)
                items = []

            for it in items:
                sym_seen += 1
                if not _within_window(it["published"], since_minutes, anchor):
                    sym_skipped += 1
                    _debug(
                        "collect.media.entry_skipped_window",
                        symbol=sym,
                        published=(it["published"].isoformat() if it.get("published") else None),
                        title_preview=(it["title"][:120] if it.get("title") else None),
                    )
                    continue
                src_host = _publisher_from_url(it["url"])
                hits.append(RawHit(sym, it["title"], it["url"], src_host, it["published"]))
                sym_matched += 1
                _debug(
                    "collect.media.entry_matched",
                    symbol=sym,
                    publisher=src_host,
                    url=it["url"],
                    published=(it["published"].isoformat() if it.get("published") else None),
                )

            _info(
                "collect.media.symbol_complete",
                symbol=sym,
                seen=sym_seen,
                skipped_window=sym_skipped,
                matched=sym_matched,
            )

        # (existing) keep:
        log.info("collect.media_done", extra={"hits_total": len(hits), "ms": _ms(t1), "run_id": _runid()})
        # (new)
        _info("collect.media_done+", hits_total=len(hits), ms=_ms(t1))
    else:
        # (existing) keep:
        log.info("collect.media_disabled", extra={"run_id": _runid()})
        # (new)
        _info("collect.media_disabled+")

    # (existing) keep:
    log.info("collect.complete", extra={"hits": len(hits), "since_min": since_minutes, "run_id": _runid()})
    # (new)
    _info("collect.complete+", hits=len(hits), since_min=since_minutes)

    return hits

@dataclass
class Cluster:
    cluster_id: str
    symbol: str
    title_rep: str
    published: datetime       # earliest
    newest_at: datetime       # newest source time
    sources: List[NewsSourceRef]
    source_count: int
    consensus_score: float
    confidence_stars: int
    sentiment: str
    event_type: str
    bullets: List[str]
    why: str

def _cluster_hits(hits: List[RawHit], weights: Dict[str, float]) -> List[Cluster]:
    t0 = _t0()
    clusters: List[Cluster] = []
    # group naïvely by (symbol) then cluster titles by token Jaccard
    by_symbol: Dict[str, List[RawHit]] = {}
    for h in hits:
        by_symbol.setdefault(h.symbol, []).append(h)

    log.info("cluster.begin", extra={"symbols": len(by_symbol), "hits": len(hits), "run_id": _runid()})
    for sym, arr in by_symbol.items():
        arr.sort(key=lambda h: (h.published or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
        used = [False] * len(arr)
        for i, h in enumerate(arr):
            if used[i]:
                continue
            base_tokens = _tokenize_title(h.title)
            group_idx = [i]
            used[i] = True
            for j in range(i + 1, len(arr)):
                if used[j]:
                    continue
                sim = _jaccard(base_tokens, _tokenize_title(arr[j].title))
                if sim >= 0.6:
                    used[j] = True
                    group_idx.append(j)

            group = [arr[k] for k in group_idx]
            # Representative title = longest
            title_rep = max((g.title for g in group), key=lambda x: len(x))
            # Earliest/newest
            pubs = [g.published for g in group if g.published]
            if pubs:
                earliest = min(pubs)
                newest = max(pubs)
            else:
                earliest = newest = _now_utc()

            # consensus
            pubs_set = set([g.publisher.lower() for g in group])
            scount = len(pubs_set)
            # base weight sum
            wsum = sum(weights.get(g.publisher.lower(), 0.9) for g in group)
            # normalize to 0..1-ish
            consensus = max(0.0, min(1.0, (wsum / max(1.0, len(group))) * (0.6 + 0.4 * min(1.0, scount / 3.0))))
            # stars
            stars = 3 if (scount >= 3 or any("nse" in g.publisher.lower() or "sebi" in g.publisher.lower() for g in group)) else 2 if scount >= 2 else 1

            # summarize (use all titles joined as context)
            context = " | ".join([g.title for g in group])[:2000]
            try:
                bullets, why, event_type, sentiment = _ollama_generate_bullets_why(context, model=(load_settings().news.summarizer or {}).get("model", "llama3"))
            except Exception:
                _exc("summarizer.unexpected_error", symbol=sym)
                bullets, why, event_type, sentiment = [title_rep], "Potentially price relevant; confirm with sources.", "other", "neutral"

            clusters.append(
                Cluster(
                    cluster_id=_hash_cluster(sym, title_rep, earliest, group[0].publisher),
                    symbol=sym,
                    title_rep=title_rep,
                    published=earliest,
                    newest_at=newest,
                    sources=[NewsSourceRef(publisher=g.publisher, url=g.url, paywalled=False) for g in group],
                    source_count=scount,
                    consensus_score=round(float(consensus), 4),
                    confidence_stars=int(stars),
                    sentiment=sentiment,
                    event_type=event_type,
                    bullets=[b for b in bullets if b][:5] or [title_rep],
                    why=why or "Potentially price relevant; confirm with sources.",
                )
            )
        log.debug("cluster.symbol_done", extra={"symbol": sym, "clusters": len(clusters), "run_id": _runid()})
    log.info("cluster.complete", extra={"clusters": len(clusters), "ms": _ms(t0), "run_id": _runid()})
    return clusters

# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def _build_batch(symbols: List[str], since_minutes: int, anchor: datetime) -> NewsIngestBatch:
    log.info("provider.build_batch_begin", extra={
        "symbols": len(symbols), "since_minutes": since_minutes, "anchor": anchor.isoformat(), "run_id": _runid()
    })
    t0 = _t0()
    smap = _load_aliases()
    weights = _build_source_weights()
    hits = _collect_hits(symbols, since_minutes, anchor, smap)
    if not hits:
        log.info("provider.no_hits", extra={"run_id": _runid()})
        return NewsIngestBatch(items=[])
    clusters = _cluster_hits(hits, weights)
    # Convert to ingest items
    items: List[NewsIngestItem] = []
    for c in clusters:
        items.append(
            NewsIngestItem(
                cluster_id=c.cluster_id,
                symbol=c.symbol,
                published=_ts_aware(c.published),
                title=c.title_rep,
                event_type=c.event_type,
                bullets=c.bullets,
                why=c.why,
                sentiment=c.sentiment,
                confidence_stars=c.confidence_stars,
                consensus_score=c.consensus_score,
                source_count=c.source_count,
                sources=c.sources,
            )
        )
    log.info("provider.build_batch_done", extra={"items": len(items), "ms": _ms(t0), "run_id": _runid()})
    return NewsIngestBatch(items=items)

def main(argv: Optional[List[str]] = None) -> int:
    s = load_settings()
    parser = argparse.ArgumentParser(description="Fetch, cluster, summarize Indian market news and print NewsIngestBatch JSON.")
    parser.add_argument("--symbols", required=True, help="Comma-separated list, e.g., RELIANCE.NS,TCS.NS")
    parser.add_argument("--since", default="10m", help="Lookback: 10m/30m/2h/1d or minutes.")
    parser.add_argument("--at", help="Anchor time ISO8601 (for backfill alignment). Defaults to now.")
    args = parser.parse_args(argv)

    symbols = [x.strip() for x in args.symbols.split(",") if x.strip()]
    if not symbols:
        _stderr("No symbols provided.")
        print(json.dumps({"items": []}))
        log.error("cli.no_symbols", extra={"run_id": _runid()})
        return 0

    since_min = _parse_since_minutes(args.since)
    anchor = _now_utc()
    if args.at:
        try:
            anchor = datetime.fromisoformat(args.at)
            if not anchor.tzinfo:
                anchor = anchor.replace(tzinfo=timezone.utc)
        except Exception:
            _stderr(f"[warn] invalid --at value; using now")
            log.warning("cli.at_invalid", extra={"at": args.at, "run_id": _runid()})

    log.info("cli.begin", extra={
        "symbols": len(symbols), "since_min": since_min, "anchor": anchor.isoformat(), "run_id": _runid()
    })

    try:
        batch = _build_batch(symbols, since_min, anchor)
        # Print strict JSON to stdout for the CLI to consume
        sys.stdout.write(batch.model_dump_json())
        sys.stdout.flush()
        log.info("cli.done", extra={"items": len(batch.items), "run_id": _runid()})
        return 0
    except Exception:
        _exc("cli.unhandled_exception")
        # Keep stdout clean on hard failures to help caller detect error
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
