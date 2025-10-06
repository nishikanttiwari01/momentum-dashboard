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

from app.core.config import REPO_ROOT, load as load_settings
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
    lg = globals().get("log")
    if not isinstance(lg, _logging.Logger):
        lg = _logging.getLogger(__name__)
    if not lg.handlers:
        h = _logging.StreamHandler()
        fmt = _logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        h.setFormatter(fmt)
        lg.addHandler(h)
    if lg.level == _logging.NOTSET or lg.level > _logging.INFO:
        lg.setLevel(_logging.INFO)
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
    if "reuters.com" not in weights:
        weights["reuters.com"] = 0.95
    log.debug("news.weights_ready", extra={"count": len(weights), "run_id": _runid()})
    return weights

# ──────────────────────────────────────────────────────────────────────────────
# Aliases & symbol master
# ──────────────────────────────────────────────────────────────────────────────

_FALLBACK_NEWS_ALIASES: dict[str, tuple[str, ...]] = {
    "ADANIENT": ("adani enterprises", "adani enterprise"),
    "ADANIPORTS": (
        "adani ports",
        "adani ports and special economic zone",
        "apsez",
    ),
    "APOLLOHOSP": ("apollo hospitals", "apollo hospital"),
    "ASIANPAINT": ("asian paints", "asian paint"),
    "AXISBANK": ("axis bank",),
    "BAJAJ-AUTO": ("bajaj auto",),
    "BAJAJFINSV": ("bajaj finserv", "bajaj financial services"),
    "BAJFINANCE": ("bajaj finance",),
    "BEL": ("bharat electronics", "bharat electronics limited"),
    "BHARTIARTL": ("bharti airtel", "airtel"),
    "BPCL": ("bharat petroleum", "bpcl"),
    "BRITANNIA": ("britannia", "britannia industries"),
    "CIPLA": ("cipla",),
    "COALINDIA": ("coal india",),
    "DIVISLAB": ("divis laboratories", "divis labs", "divi's laboratories"),
    "DRREDDY": (
        "dr reddy",
        "dr reddys",
        "dr reddy's laboratories",
        "dr reddys laboratories",
    ),
    "EICHERMOT": ("eicher motors",),
    "ETERNAL": ("eternal", "eternal limited"),
    "GRASIM": ("grasim industries", "grasim"),
    "HCLTECH": ("hcl technologies", "hcl tech"),
    "HDFCBANK": ("hdfc bank",),
    "HDFCLIFE": ("hdfc life", "hdfc life insurance"),
    "HEROMOTOCO": ("hero motocorp", "hero moto corp"),
    "HINDALCO": ("hindalco", "hindalco industries"),
    "HINDUNILVR": ("hindustan unilever", "hul"),
    "ICICIBANK": ("icici bank",),
    "INDUSINDBK": ("indusind bank",),
    "INFY": ("infosys",),
    "ITC": ("itc", "itc limited"),
    "JIOFIN": (
        "jio financial services",
        "jio finance",
        "jio financial",
    ),
    "JSWSTEEL": ("jsw steel",),
    "KOTAKBANK": ("kotak bank", "kotak mahindra bank"),
    "LT": ("larsen & toubro", "larsen and toubro", "l&t"),
    "LTIM": ("ltimindtree", "ltim mindtree", "ltim"),
    "M&M": ("mahindra & mahindra", "mahindra and mahindra", "mahindra"),
    "MARUTI": ("maruti suzuki", "maruti suzuki india"),
    "NESTLEIND": ("nestle india",),
    "NTPC": ("ntpc", "national thermal power"),
    "ONGC": ("ongc", "oil and natural gas corporation"),
    "POWERGRID": ("power grid", "power grid corporation"),
    "RELIANCE": ("reliance", "reliance industries", "ril"),
    "SBILIFE": ("sbi life", "sbi life insurance"),
    "SBIN": ("state bank of india", "sbi"),
    "SHRIRAMFIN": ("shriram finance", "shriram finance limited"),
    "SUNPHARMA": ("sun pharma", "sun pharmaceutical"),
    "TATACONSUM": ("tata consumer", "tata consumer products"),
    "TATAMOTORS": ("tata motors",),
    "TATASTEEL": ("tata steel",),
    "TCS": ("tata consultancy services", "tcs"),
    "TECHM": ("tech mahindra",),
    "TITAN": ("titan", "titan company"),
    "TRENT": ("trent", "trent limited"),
    "ULTRACEMCO": ("ultratech cement", "ultra tech cement"),
    "UPL": ("upl", "upl limited"),
    "WIPRO": ("wipro",),
}

_SUFFIX_REPLACEMENTS: dict[str, str] = {
    "bk": "bank",
    "bank": "bank",
    "banks": "bank",
    "finserv": "financial services",
    "finsv": "financial services",
    "finance": "finance",
    "fin": "finance",
    "life": "life",
    "motors": "motors",
    "motor": "motor",
    "ports": "ports",
    "port": "port",
    "steel": "steel",
    "energy": "energy",
    "power": "power",
    "chem": "chem",
    "chemicals": "chemicals",
    "infra": "infra",
    "telecom": "telecom",
    "tech": "tech",
    "technologies": "technologies",
    "services": "services",
    "service": "service",
    "india": "india",
    "ind": "india",
    "enterprises": "enterprises",
    "enterprise": "enterprise",
    "ent": "enterprise",
    "paints": "paints",
    "paint": "paints",
    "hospitals": "hospitals",
    "hospital": "hospital",
    "hosp": "hospital",
    "labs": "labs",
    "lab": "labs",
    "cement": "cement",
    "grid": "grid",
    "consum": "consumer",
    "consumer": "consumer",
    "foods": "foods",
    "retail": "retail",
    "airtel": "airtel",
    "ltd": "limited",
}


def _resolve_config_path(path_str: Optional[str]) -> Optional[Path]:
    if not path_str:
        return None
    candidate = Path(path_str).expanduser()
    if candidate.exists():
        return candidate
    if candidate.is_absolute():
        return None
    raw = path_str.replace('\\', '/').lstrip('./')
    alternatives = []
    alternatives.append((REPO_ROOT / raw).resolve())
    if raw.startswith('config/'):
        alternatives.append((REPO_ROOT / 'configs' / raw.split('/', 1)[1]).resolve())
    alternatives.append((REPO_ROOT / 'backend' / raw).resolve())
    resolved = set()
    for alt in alternatives:
        if alt in resolved:
            continue
        resolved.add(alt)
        if alt.exists():
            return alt
    return None


def _heuristic_aliases(sym: str) -> Set[str]:
    base = sym.split('.', 1)[0]
    lower = base.lower()
    clean = re.sub(r'[^a-z0-9]', '', lower)
    results: Set[str] = set()
    if lower:
        results.add(lower)
    if clean:
        results.add(clean)
    if '&' in lower:
        results.add(lower.replace('&', ' & '))
        results.add(lower.replace('&', ' and '))
        results.add(lower.replace('&', ' '))
    if clean:
        spaced = re.sub(r'([a-z])([0-9])', r'\1 \2', clean)
        spaced = re.sub(r'([0-9])([a-z])', r'\1 \2', spaced)
        if spaced and spaced != clean:
            results.add(spaced)
        for suffix, replacement in _SUFFIX_REPLACEMENTS.items():
            if clean.endswith(suffix) and len(clean) > len(suffix):
                prefix = clean[:-len(suffix)]
                if prefix:
                    results.add(f"{prefix} {replacement}".strip())
                    results.add(f"{prefix}{replacement}".strip())
    if lower.startswith('dr') and len(lower) > 2:
        tail = lower[2:]
        results.add(f"dr {tail}".strip())
        results.add(f"doctor {tail}".strip())
    return {
        alias.strip()
        for alias in results
        if alias.strip() and len(re.sub(r'[^a-z0-9]', '', alias)) >= 3
    }


def _candidate_phrases(sym: str, smap: SymbolMap) -> Set[str]:
    variants = {sym}
    root = sym.split('.', 1)[0]
    variants.add(root)
    variants.add(root.upper())
    variants.add(root.lower())
    phrases: Set[str] = set()
    for variant in variants:
        phrases.update(smap.match.get(variant, set()))
    fallback = _FALLBACK_NEWS_ALIASES.get(root.upper())
    if fallback:
        phrases.update(fallback)
    phrases.update(_heuristic_aliases(sym))
    return {p.strip().lower() for p in phrases if p}

@dataclass
class SymbolMap:
    # symbol -> set of matchable phrases
    match: Dict[str, Set[str]]

def _load_aliases() -> SymbolMap:
    cfg = load_settings().news.mapping or {}
    alias_path = _resolve_config_path(cfg.get("aliases_csv"))
    master_path = _resolve_config_path(cfg.get("nse_master_csv"))
    match: Dict[str, Set[str]] = {}

    def add(sym: str, phrase: str) -> None:
        sym = sym.strip()
        phrase = phrase.strip()
        if not sym or not phrase:
            return
        match.setdefault(sym, set()).add(phrase.lower())

    if alias_path:
        t0 = _t0()
        with open(alias_path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                add(row.get("symbol", ""), row.get("alias", ""))
        log.info(
            "news.aliases_loaded",
            extra={"path": str(alias_path), "symbols": len(match), "ms": _ms(t0), "run_id": _runid()},
        )
    elif cfg.get("aliases_csv"):
        _debug("news.aliases_missing", path=cfg.get("aliases_csv"))

    if master_path:
        t0 = _t0()
        with open(master_path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                add(row.get("symbol", ""), row.get("company_name", ""))
        log.info(
            "news.master_loaded",
            extra={"path": str(master_path), "symbols": len(match), "ms": _ms(t0), "run_id": _runid()},
        )
    elif cfg.get("nse_master_csv"):
        _debug("news.master_missing", path=cfg.get("nse_master_csv"))

    for sym_root, aliases in _FALLBACK_NEWS_ALIASES.items():
        for alias in aliases:
            add(sym_root, alias)
            add(f"{sym_root}.NS", alias)

    for sym in list(match.keys()):
        base = sym.split(".")[0]
        add(sym, base)
        add(base, base)
        base_spaced = base.replace('_', ' ').replace('-', ' ')
        if '&' in base_spaced:
            base_spaced_amp = base_spaced.replace('&', ' & ')
            add(sym, base_spaced_amp)
            add(base, base_spaced_amp)
            add(sym, base_spaced_amp.replace(' & ', ' and '))
            add(base, base_spaced_amp.replace(' & ', ' and '))
        else:
            add(sym, base_spaced)
            add(base, base_spaced)

    log.debug("news.alias_map_ready", extra={"symbols": len(match), "run_id": _runid()})
    return SymbolMap(match=match)


def _headline_matches_symbol(headline: str, sym: str, smap: SymbolMap) -> bool:
    hay = _norm_text(headline).lower()
    hay_norm = re.sub(r'[^a-z0-9]', '', hay)
    for phrase in _candidate_phrases(sym, smap):
        phrase = phrase.strip().lower()
        if not phrase:
            continue
        phrase_norm = re.sub(r'[^a-z0-9]', '', phrase)
        if len(phrase_norm) < 3:
            continue
        if phrase in hay:
            return True
        if phrase_norm and phrase_norm in hay_norm:
            return True
        tokens = [tok for tok in phrase.split() if len(tok) >= 2]
        if tokens and all(tok in hay for tok in tokens):
            return True
    return False

# ──────────────────────────────────────────────────────────────────────────────
# Fetchers (RSS + Google News RSS + NSE JSON optional)
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

    CONNECT_TO = min(8, timeout)
    READ_TO    = max(4, min(12, timeout))
    RETRIES    = 2
    UA = os.getenv("NEWS_RSS_UA", "Mozilla/5.0 (compatible; MomentumSuite/1.0; +https://localhost)")

    _info("rss.fetch_start", url=url, connect_to=CONNECT_TO, read_to=READ_TO, retries=RETRIES)
    last_err = None

    for attempt in range(1, RETRIES + 2):
        try:
            try:
                requests.head(url, timeout=(CONNECT_TO, 3), headers={"User-Agent": UA})
            except Exception:
                pass

            resp = requests.get(url, timeout=(CONNECT_TO, READ_TO), headers={"User-Agent": UA})
            resp.raise_for_status()
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
            try:
                time.sleep(0.6 * attempt)
            except Exception:
                pass

    _error("rss.fetch_failed", url=url, err=str(last_err)[:300], ms=_ms(t0))
    return out

def _nse_session() -> requests.Session:
    """
    Create a browser-like session for NSE JSON endpoints (Akamai).
    Performs a warm-up GET to seed cookies.
    """
    s = requests.Session()
    headers = {
        "User-Agent": os.getenv("NEWS_UA", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    s.headers.update(headers)
    try:
        s.get("https://www.nseindia.com/", timeout=(8, 12))
    except Exception:
        pass
    return s

def _fetch_nse_corporate_json(url: str, timeout: int = 20) -> List[dict]:
    """
    Fetch NSE Corporate Announcements JSON and convert to our entry dicts:
      { title, url, published }
    Expects response with 'data' list where each item has 'headline' and 'sl' (or similar).
    """
    out: List[dict] = []
    s = _nse_session()
    try:
        resp = s.get(url, timeout=(8, timeout))
        resp.raise_for_status()
        js = resp.json()
    except Exception as e:
        _warn("nse.json_fetch_failed", url=url, err=str(e)[:200])
        return out

    rows = js.get("data") or js.get("rows") or []
    for r in rows:
        title = _norm_text(r.get("headline") or r.get("subject") or r.get("company") or "")
        link = r.get("pdfUrl") or r.get("url") or ""
        # Construct announcement link when only 'sl' is present
        if not link and r.get("sl"):
            link = f"https://www.nseindia.com/companies-listing/corporate-filings-announcements?symbol={quote_plus(str(r.get('symbol') or ''))}"
        # Parse published date/time
        pub = None
        for k in ("disseminationTime", "dt", "time", "date"):
            if r.get(k):
                try:
                    val = str(r.get(k))
                    # common format "2025-10-04T12:34:56"
                    pub = datetime.fromisoformat(val.replace("Z", "+00:00"))
                    if not pub.tzinfo:
                        pub = pub.replace(tzinfo=timezone.utc)
                    break
                except Exception:
                    pass
        out.append({"title": title, "url": link, "published": pub})
    _info("nse.json_fetch_ok", url=url, items=len(out))
    return out

def _google_news_rss(site: str, query: str) -> str:
    base = "https://news.google.com/rss/search?q="
    q = f"site:{site} ({quote_plus(query)}) when:24h"
    return f"{base}{q}&hl=en-IN&gl=IN&ceid=IN:en"

def _fetch_media_for_symbol(sym: str, aliases: List[str], sites: List[str]) -> List[dict]:
    items: List[dict] = []
    query = " OR ".join([sym.split(".")[0]] + aliases[:2])
    for site in sites:
        url = _google_news_rss(site, query)
        items.extend(_fetch_rss(url))
    log.debug("media.symbol_fetched", extra={"symbol": sym, "sites": len(sites), "items": len(items), "run_id": _runid()})
    return items

# ──────────────────────────────────────────────────────────────────────────────
# Summarizer (Ollama optional) + lightweight fallback + optional article fetch
# ──────────────────────────────────────────────────────────────────────────────

def _ollama_generate_bullets_why(text: str, model: str = "llama3", timeout: int = 20) -> Tuple[List[str], str, str, str]:
    """
    Returns (bullets, why, event_type, sentiment). If Ollama unavailable, raises → caller will fallback.
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
    t0 = _t0()
    payload = {"model": model, "prompt": prompt, "stream": False, "options": {"num_predict": 256}}
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    content = resp.json().get("response", "").strip()
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

def _fallback_summarize(text: str) -> Tuple[List[str], str, str, str]:
    """
    Use the lightweight summarizer if present; else a safe heuristic.
    Returns (bullets, why, event_type, sentiment).
    """
    try:
        from backend.app.nlp.summarizer import summarize_to_bullets
        bullets, why = summarize_to_bullets("", text, max_bullets=3)
        bullets = bullets or [text.split(".")[0][:140]]
        why = why or "Key update relevant to near-term price action"
        return bullets, why, "other", "neutral"
    except Exception as e:
        log.info("fallback_summarizer.unavailable", extra={"reason": str(e)[:140], "run_id": _runid()})
        head = _norm_text(text).split(".")[0][:140]
        return [head] if head else [], "Potentially price relevant; confirm with sources.", "other", "neutral"

def _enrich_from_article(primary_url: str) -> Tuple[List[str], str]:
    """
    Best-effort: fetch the article and produce bullets/why using lightweight summarizer.
    Silent no-op if content_fetcher is unavailable or fetch fails.
    """
    try:
        from backend.app.pipeline.content_fetcher import fetch_and_summarize
        data = fetch_and_summarize(primary_url, max_bullets=3)
        bullets = data.get("bullets") or []
        why = data.get("why") or ""
        return bullets[:5], why
    except Exception as e:
        log.debug("content_fetch_skip", extra={"reason": str(e)[:120], "url": primary_url, "run_id": _runid()})
        return [], ""

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
    """
    Intraday: anchor ≈ now → [anchor - since, anchor + 5m]
    Backfill: anchor is in the past (by >2h) → [anchor, anchor + since]
    """
    if pub is None:
        return True
    if pub.tzinfo is None:
        pub = pub.replace(tzinfo=timezone.utc)

    now_utc = datetime.now(timezone.utc)
    anchor = anchor if anchor.tzinfo else anchor.replace(tzinfo=timezone.utc)

    # Heuristic: if anchor is >2h behind 'now', we treat this as a backfill anchor.
    if (now_utc - anchor) > timedelta(hours=2):
        start = anchor
        end = anchor + timedelta(minutes=since_minutes)
    else:
        start = anchor - timedelta(minutes=since_minutes)
        end = anchor + timedelta(minutes=5)

    return start <= pub <= end

def _collect_hits(symbols: List[str], since_minutes: int, anchor: datetime, smap: SymbolMap) -> List[RawHit]:
    s = load_settings()
    t0 = _t0()
    hits: List[RawHit] = []

    # Official feeds (support RSS and optional NSE JSON)
    official = s.news.sources.get("official") or []
    log.info("collect.official_begin", extra={"feeds": len(official), "run_id": _runid()})
    _info("collect.official_begin+", feeds=len(official), since_min=since_minutes, anchor=anchor.isoformat(), symbols=len(symbols))

    for src in official:
        url = src.get("url")
        if not url:
            _debug("collect.official.skip_no_url", src=src)
            continue

        mode = (src.get("mode") or "rss").strip().lower()
        feed_seen = 0
        feed_skipped_window = 0
        feed_matched = 0
        _debug("collect.official.feed_start", url=url, mode=mode)

        if mode == "nse_json":
            entries = _fetch_nse_corporate_json(url)
        else:
            entries = _fetch_rss(url)

        for ent in entries:
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
            mode=mode,
        )

    log.info("collect.official_done", extra={"hits": len(hits), "ms": _ms(t0), "run_id": _runid()})
    _info("collect.official_done+", hits=len(hits), ms=_ms(t0))

    # Media via Google News (site-filtered)
    gcfg = s.news.sources.get("google_news") or s.news.get("google_news") or {}
    if gcfg and (gcfg.get("enabled", True)):
        sites = list(gcfg.get("sites") or [])
        log.info("collect.media_begin", extra={"sites": len(sites), "symbols": len(symbols), "run_id": _runid()})
        _info("collect.media_begin+", sites=len(sites), symbols=len(symbols))

        t1 = _t0()
        alias_map: Dict[str, List[str]] = {}
        for sym in symbols:
            variants = set(smap.match.get(sym, set()))
            variants.update(smap.match.get(sym.split('.', 1)[0], set()))
            alias_map[sym] = sorted(variants, key=len, reverse=True)
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

        log.info("collect.media_done", extra={"hits_total": len(hits), "ms": _ms(t1), "run_id": _runid()})
        _info("collect.media_done+", hits_total=len(hits), ms=_ms(t1))
    else:
        log.info("collect.media_disabled", extra={"run_id": _runid()})
        _info("collect.media_disabled+")

    log.info("collect.complete", extra={"hits": len(hits), "since_min": since_minutes, "run_id": _runid()})
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
            title_rep = max((g.title for g in group), key=lambda x: len(x))
            pubs = [g.published for g in group if g.published]
            if pubs:
                earliest = min(pubs)
                newest = max(pubs)
            else:
                earliest = newest = _now_utc()

            pubs_set = set([g.publisher.lower() for g in group])
            scount = len(pubs_set)
            wsum = sum(weights.get(g.publisher.lower(), 0.9) for g in group)
            consensus = max(0.0, min(1.0, (wsum / max(1.0, len(group))) * (0.6 + 0.4 * min(1.0, scount / 3.0))))
            stars = 3 if (scount >= 3 or any("nse" in g.publisher.lower() or "sebi" in g.publisher.lower() for g in group)) else 2 if scount >= 2 else 1

            # Summarization strategy:
            # 1) Try to enrich from the first source article (fast, fallback-safe).
            # 2) If still empty, try Ollama if available.
            # 3) If Ollama not available, use the lightweight summarizer (fallback).
            primary_url = group[0].url if group and group[0].url else ""
            bullets, why = _enrich_from_article(primary_url) if primary_url else ([], "")
            event_type, sentiment = "other", "neutral"

            if not bullets:
                context = " | ".join([g.title for g in group])[:2000]
                try:
                    b2, w2, et2, se2 = _ollama_generate_bullets_why(context, model=(load_settings().news.summarizer or {}).get("model", "llama3"))
                    bullets = b2 or bullets
                    why = w2 or why
                    event_type = et2 or event_type
                    sentiment = se2 or sentiment
                except Exception:
                    b3, w3, et3, se3 = _fallback_summarize(context)
                    bullets = bullets or b3
                    why = why or w3
                    event_type = et3 or event_type
                    sentiment = se3 or sentiment

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
        sys.stdout.write(batch.model_dump_json())
        sys.stdout.flush()
        log.info("cli.done", extra={"items": len(batch.items), "run_id": _runid()})
        return 0
    except Exception:
        _exc("cli.unhandled_exception")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
