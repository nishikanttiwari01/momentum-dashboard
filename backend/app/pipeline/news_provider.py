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



from app.core.config import load as load_settings
from app.schemas.generated.models import (
    NewsIngestBatch,
    NewsIngestItem,
    NewsSourceRef,
)

# ──────────────────────────────────────────────────────────────────────────────
# Utils
# ──────────────────────────────────────────────────────────────────────────────

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
        with open(alias_csv, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                add(row.get("symbol", ""), row.get("alias", ""))

    # nse_master.csv: symbol,isin,company_name,sector
    if master_csv and Path(master_csv).exists():
        with open(master_csv, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                add(row.get("symbol", ""), row.get("company_name", ""))

    # fallback: symbol itself
    for sym in list(match.keys()):
        add(sym, sym.split(".")[0])  # e.g., RELIANCE from RELIANCE.NS

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
    try:
        parsed = feedparser.parse(url)
        out: List[dict] = []
        for e in parsed.entries:
            title = _norm_text(e.get("title", ""))
            link = e.get("link") or ""
            published = None
            for key in ("published_parsed", "updated_parsed"):
                if e.get(key):
                    published = datetime(*e[key][:6], tzinfo=timezone.utc)
                    break
            out.append({"title": title, "url": link, "published": published})
        return out
    except Exception as e:
        _stderr(f"[warn] RSS fetch failed {url}: {e}")
        return []

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
        return bullets, why, event_type, sentiment
    except Exception as e:
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
    hits: List[RawHit] = []

    # Official feeds (not symbol-specific, filter by aliases)
    official = s.news.sources.get("official") or []
    for src in official:
        url = src.get("url")
        if not url:
            continue
        for ent in _fetch_rss(url):
            title = ent["title"]
            pub = ent["published"]
            if not _within_window(pub, since_minutes, anchor):
                continue
            pubr = src.get("name") or _publisher_from_url(url)
            link = ent["url"]
            # Map to symbols by alias match
            for sym in symbols:
                if _headline_matches_symbol(title, sym, smap):
                    hits.append(RawHit(sym, title, link, pubr, pub))

    # Media via Google News (site-filtered)
    gcfg = s.news.sources.get("google_news") or s.news.get("google_news") or {}
    if gcfg and (gcfg.get("enabled", True)):
        sites = list(gcfg.get("sites") or [])
        # build quick alias map list for speed
        alias_map: Dict[str, List[str]] = {sym: list(smap.match.get(sym, set())) for sym in symbols}
        for sym in symbols:
            try:
                items = _fetch_media_for_symbol(sym, alias_map.get(sym, []), sites)
            except Exception as e:
                _stderr(f"[warn] media fetch failed for {sym}: {e}")
                items = []
            for it in items:
                if not _within_window(it["published"], since_minutes, anchor):
                    continue
                hits.append(RawHit(sym, it["title"], it["url"], _publisher_from_url(it["url"]), it["published"]))
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
    clusters: List[Cluster] = []
    # group naïvely by (symbol) then cluster titles by token Jaccard
    by_symbol: Dict[str, List[RawHit]] = {}
    for h in hits:
        by_symbol.setdefault(h.symbol, []).append(h)

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
            bullets, why, event_type, sentiment = _ollama_generate_bullets_why(context, model=(load_settings().news.summarizer or {}).get("model", "llama3"))

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
    return clusters

# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def _build_batch(symbols: List[str], since_minutes: int, anchor: datetime) -> NewsIngestBatch:
    smap = _load_aliases()
    weights = _build_source_weights()
    hits = _collect_hits(symbols, since_minutes, anchor, smap)
    if not hits:
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

    batch = _build_batch(symbols, since_min, anchor)
    # Print strict JSON to stdout for the CLI to consume
    sys.stdout.write(batch.model_dump_json())
    sys.stdout.flush()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

