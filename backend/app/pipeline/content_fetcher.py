# backend/app/pipeline/content_fetcher.py
from __future__ import annotations

import re
import html
import json
from dataclasses import dataclass
from typing import Optional, Tuple

# stdlib HTTP with timeouts
import urllib.request
import urllib.error

# Optional BeautifulSoup (if available in your venv)
try:
    from bs4 import BeautifulSoup  # type: ignore
except Exception:
    BeautifulSoup = None  # type: ignore

_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://news.google.com/",
}

@dataclass
class FetchConfig:
    connect_timeout_sec: int = 12
    read_timeout_sec: int = 20
    user_agent: str = _DEFAULT_HEADERS["User-Agent"]
    allow_languages: tuple[str, ...] = ("en",)
    readabilize: bool = True
    keep_paywalled_title_only: bool = True

def _http_get(url: str, headers: Optional[dict] = None, timeout: int = 25) -> Tuple[int, str, dict]:
    hdrs = dict(_DEFAULT_HEADERS)
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            code = resp.getcode()
            return code, body, dict(resp.headers)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        return e.code, body, dict(getattr(e, "headers", {}) or {})
    except Exception as e:
        return 0, repr(e), {}

_META_TITLE_PAT = re.compile(r"<title>(.*?)</title>", re.I | re.S)
_OG_TITLE_PAT = re.compile(r'<meta\s+property=["\']og:title["\']\s+content=["\'](.*?)["\']', re.I)
_DESC_PAT = re.compile(r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']', re.I)
_OG_DESC_PAT = re.compile(r'<meta\s+property=["\']og:description["\']\s+content=["\'](.*?)["\']', re.I)

def _strip_html(text: str) -> str:
    # Fallback when BeautifulSoup not present
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def _readability_bs4(html_text: str) -> Tuple[str, str]:
    """
    Very simple article extractor using BeautifulSoup if installed.
    Returns (title, text). If bs4 unavailable, returns ("", "").
    """
    if BeautifulSoup is None:
        return "", ""
    soup = BeautifulSoup(html_text, "html.parser")
    # Title preference: og:title > title
    ogt = soup.find("meta", {"property": "og:title"})
    title = (ogt and ogt.get("content")) or (soup.title.string if soup.title else "") or ""
    # Greedy extraction: prefer <article>, else the longest <p> block cluster
    article = soup.find("article")
    paragraphs = []
    if article:
        paragraphs = [p.get_text(" ", strip=True) for p in article.find_all("p")]
    else:
        candidates = soup.find_all("p")
        paragraphs = [p.get_text(" ", strip=True) for p in candidates]
        # Keep the densest middle part
        paragraphs = [p for p in paragraphs if len(p.split()) >= 6]
    body = "\n".join(paragraphs)[:12000]
    return (title or "").strip(), (body or "").strip()

def fetch_article(
    url: str,
    headers: Optional[dict] = None,
    cfg: Optional[FetchConfig] = None,
) -> Tuple[str, str, bool]:
    """
    Fetch an article URL and return (title, text, paywalled).
    - Uses og:title/description, <title>, and a bs4 read if available.
    - Marks paywalled heuristically if body is empty but we have a title.
    """
    cfg = cfg or FetchConfig()
    # merged headers with UA
    hdrs = {"User-Agent": cfg.user_agent, **(headers or {})}
    code, body, resp_headers = _http_get(url, headers=hdrs, timeout=cfg.read_timeout_sec)
    if code == 0:
        # network error; return empty but safe
        return "", "", False

    # Try OpenGraph/meta first (cheap and often good)
    og_title = (_OG_TITLE_PAT.search(body) or _META_TITLE_PAT.search(body) or _DESC_PAT.search(body) or _OG_DESC_PAT.search(body))
    meta_title = ""
    if og_title:
        meta_title = html.unescape(og_title.group(1)).strip()

    # If bs4 present, try to extract article text
    art_title, art_text = _readability_bs4(body)

    title = (art_title or meta_title or "").strip()
    text = art_text.strip()

    if not text:
        # Fallback: strip HTML for a crude body; if still empty, treat as possibly paywalled
        stripped = _strip_html(body)
        # Avoid returning the entire page chrome; cap length
        text = stripped[:12000]
    paywalled = False
    if cfg.keep_paywalled_title_only and not text and title:
        paywalled = True

    return title, text, paywalled

# Convenience helper for the provider:
def fetch_and_summarize(url: str, headers: Optional[dict] = None, cfg: Optional[FetchConfig] = None, max_bullets: int = 3) -> dict:
    """
    Returns: { title, text, paywalled, bullets, why }
    """
    from backend.app.nlp.summarizer import summarize_article  # local import to avoid hard dep if unused
    t, body, pw = fetch_article(url, headers=headers, cfg=cfg)
    summ = summarize_article(t, body, max_bullets=max_bullets)
    return {"title": t, "text": body, "paywalled": pw, **summ}
