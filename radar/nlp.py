from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "into", "after", "over", "under", "today",
    "latest", "live", "news", "update", "updates", "india", "indian", "will", "what", "when", "where",
    "why", "how", "about", "amid", "says", "said", "new", "old", "now", "are", "was", "were", "been",
    "have", "has", "had", "not", "you", "your", "their", "they", "his", "her", "its", "our", "out", "all",
    "more", "less", "than", "then", "also", "first", "last", "top", "big", "watch", "video",
}
SOURCE_NOISE = {
    "ani", "afp", "ap", "pti", "reuters", "bloomberg", "bbc", "cnn", "nbc", "cnbc", "ndtv",
    "espn", "espncricinfo", "hindustan", "toi", "times", "india", "express", "indianexpress",
    "livemint", "mint", "businessline", "thehindu", "hindu", "news18", "zeenews", "zee",
    "firstpost", "deccan", "herald", "tribune", "wire", "agency", "source", "google", "yahoo",
}

DESK_KEYWORDS = {
    "Politics": {"modi", "rahul", "gandhi", "bjp", "congress", "election", "parliament", "minister", "govt", "government", "cm", "pm"},
    "World": {"iran", "israel", "us", "russia", "china", "pakistan", "ukraine", "gaza", "trump", "war", "global"},
    "Business": {"sensex", "nifty", "stock", "market", "rbi", "rupee", "gold", "bank", "economy", "ipo", "gst"},
    "Sports": {"cricket", "ipl", "icc", "bcci", "kohli", "rohit", "football", "match", "world cup", "test"},
    "Entertainment": {"bollywood", "actor", "actress", "film", "movie", "ott", "trailer", "box office", "celebrity"},
    "Technology": {"ai", "iphone", "google", "openai", "meta", "tesla", "tech", "startup", "app"},
    "Health": {"health", "covid", "doctor", "hospital", "disease", "medicine", "pregnancy", "vaccine"},
    "Education": {"neet", "jee", "exam", "nta", "counselling", "result", "admit card", "school", "college"},
    "Crime": {"murder", "arrest", "police", "crime", "fir", "court", "accused", "case"},
    "Lifestyle": {"weather", "rain", "monsoon", "travel", "food", "astrology", "horoscope", "fashion"},
}


def normalize_text(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^a-z0-9\s\-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize(text: str) -> list[str]:
    return [t for t in normalize_text(text).split() if len(t) > 2 and t not in STOPWORDS and t not in SOURCE_NOISE]


def top_keywords(texts: Iterable[str], n: int = 12) -> list[str]:
    counts = Counter()
    for text in texts:
        counts.update(tokenize(text))
    return [w for w, _ in counts.most_common(n)]


def extract_entities(text: str, max_entities: int = 12) -> list[str]:
    if not text:
        return []
    # Conservative: capture title-case names/acronyms and known high-signal tokens.
    title_entities = re.findall(r"\b(?:[A-Z][a-z]+|[A-Z]{2,})(?:\s+(?:[A-Z][a-z]+|[A-Z]{2,}))*\b", text)
    acronym_entities = re.findall(r"\b[A-Z]{2,}\b", text)
    known = []
    low = normalize_text(text)
    for desk_terms in DESK_KEYWORDS.values():
        for term in desk_terms:
            if term in low and term not in known:
                known.append(term.title())
    merged = []
    for ent in acronym_entities + title_entities + known:
        ent = ent.strip()
        if len(ent) < 3:
            continue
        if ent.lower().replace(" ", "") in SOURCE_NOISE or ent.lower() in STOPWORDS:
            continue
        if ent not in merged:
            merged.append(ent)
    return merged[:max_entities]


def infer_desk(text: str) -> str:
    low = normalize_text(text)
    scores = {}
    for desk, terms in DESK_KEYWORDS.items():
        score = 0
        for term in terms:
            if term in low:
                score += 1
        if score:
            scores[desk] = score
    if not scores:
        return "National"
    return max(scores.items(), key=lambda x: x[1])[0]


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def headline_from_keywords(keywords: list[str], fallback: str = "Untitled Topic") -> str:
    if not keywords:
        return fallback[:90]
    return " ".join(k.title() for k in keywords[:5])
