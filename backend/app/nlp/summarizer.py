# backend/app/nlp/summarizer.py
from __future__ import annotations

import re
import math
from collections import Counter
from typing import List, Tuple, Iterable, Optional

_NUM_PAT = re.compile(
    r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?:\s?(?:%|pct|crore|cr|lakh|mn|bn|million|billion|₹|rs\.?|rupees))?",
    re.I,
)
_CHANGE_VERBS = {
    "rise","rises","rose","increase","increases","increased","grow","grows","grew",
    "jump","jumps","jumped","surge","surges","surged","improve","improves","improved",
    "fall","falls","fell","decline","declines","declined","drop","drops","dropped",
    "cut","cuts","cutting","raise","raises","raised","lift","lifts","lifted",
    "approve","approves","approved","award","awards","awarded","win","wins","won",
    "launch","launches","launched","expand","expands","expanded",
    "appoint","appoints","appointed","resign","resigns","resigned",
    "acquire","acquires","acquired","merge","merges","merged","invest","invests","invested",
}
_LABEL_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("Results/Guidance", re.compile(r"\b(q[1-4]|fy\d{2}|revenue|profit|ebitda|margin|guidance|pat|eps)\b", re.I)),
    ("Board/Regulatory", re.compile(r"\b(board|director|dividend|record date|buyback|agm|egm|regulator|sebi)\b", re.I)),
    ("Deal/M&A",        re.compile(r"\b(acquire|acquisition|stake|merger|deal|binding|definitive|mou)\b", re.I)),
    ("Order Win/Project", re.compile(r"\b(order|contract|loi|project|capex|greenfield|brownfield|capacity|mw|mtpa)\b", re.I)),
    ("Debt/Rating",     re.compile(r"\b(rating|crisil|care|icra|downgrade|upgrade|ncd|debenture|bond|notes)\b", re.I)),
]

_SENT_SPLIT = re.compile(r"(?<=[.?!])\s+(?=[A-Z(])")

def _sentences(text: str) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    # Keep simple – split on end punctuation + whitespace
    sents = _SENT_SPLIT.split(text)
    # Normalize whitespace
    return [re.sub(r"\s+", " ", s).strip() for s in sents if s.strip()]

def _tokens(s: str) -> List[str]:
    # Lowercase words with basic filtering
    return re.findall(r"[A-Za-z][A-Za-z0-9\-&']+", s.lower())

def _idf(corpus_sents: Iterable[str]) -> Counter:
    # Very light IDF proxy: penalize overly common words across sentences
    df = Counter()
    total = 0
    for s in corpus_sents:
        total += 1
        df.update(set(_tokens(s)))
    idf = Counter()
    if total == 0:
        return idf
    for w, d in df.items():
        # +1 smoothing to avoid div by zero; clamp
        idf[w] = math.log(1.0 + (total / (1 + d)))
    return idf

def _score_sentence(s: str, idf: Counter) -> float:
    toks = _tokens(s)
    if not toks:
        return 0.0
    tf = Counter(toks)
    # TF-IDF sum
    score = sum((tf[w] * idf.get(w, 1.0)) for w in tf)
    # Boost if numeric info present
    if _NUM_PAT.search(s):
        score *= 1.25
    # Boost for change verbs / action words
    if any(v in toks for v in _CHANGE_VERBS):
        score *= 1.15
    # Slightly favor shorter, denser sentences
    length_penalty = 1.0 + min(0.2, max(0.0, (len(s) - 240) / 1000.0))
    score = score / length_penalty
    return score

def _label_for(text: str) -> str:
    t = (text or "")
    for label, pat in _LABEL_PATTERNS:
        if pat.search(t):
            return label
    return "Other"

def summarize_to_bullets(
    title: str,
    body_text: str,
    max_bullets: int = 3,
) -> Tuple[List[str], str]:
    """
    Return (bullets, why) given a headline and article body.
    - Bullets: 1..max_bullets concise lines.
    - Why: a one-line rationale (category + distilled takeaway).
    """
    # Build sentence list (title first as a strong cue)
    sents = []
    title = (title or "").strip()
    if title:
        sents.append(title)
    sents.extend(_sentences(body_text or ""))

    # De-dup near-identical sentences
    seen = set()
    uniq = []
    for s in sents:
        key = re.sub(r"[^A-Za-z0-9]+", "", s.lower())[:140]
        if key in seen:
            continue
        seen.add(key)
        uniq.append(s)

    if not uniq:
        return [], ""

    idf = _idf(uniq)
    ranked = sorted(((s, _score_sentence(s, idf)) for s in uniq), key=lambda t: t[1], reverse=True)

    # Build bullets from top sentences (skip the headline if too similar)
    bullets: List[str] = []
    used_keys = set()
    for s, _ in ranked:
        # Avoid headline echo
        if title and s != title:
            base = re.sub(r"\s+", " ", s).strip()
            # Trim trailing period and overlong sentences
            base = base[:-1] if base.endswith(".") else base
            if len(base) > 220:
                base = base[:217].rstrip() + "…"
            k = re.sub(r"[^A-Za-z0-9]+", "", base.lower())[:120]
            if k in used_keys:
                continue
            used_keys.add(k)
            bullets.append(f"• {base}")
        if len(bullets) >= max_bullets:
            break

    # If we failed to pick any, fall back to title
    if not bullets and title:
        bullets = ["• " + title]

    # Build a compact "why" line
    label = _label_for(title + " " + (body_text or ""))
    # Pull a key number if any
    m = _NUM_PAT.search(title) or _NUM_PAT.search(body_text or "")
    nugget = (m.group(0) if m else "").strip()
    why = f"{label}: " + (nugget if nugget else "Key update relevant to near-term price action")

    return bullets, why

# Convenience façade expected by pipeline
def summarize_article(title: str, text: str, max_bullets: int = 3) -> dict:
    bullets, why = summarize_to_bullets(title, text, max_bullets=max_bullets)
    return {"bullets": bullets, "why": why}
