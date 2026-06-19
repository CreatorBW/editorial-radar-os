from __future__ import annotations

import html
import re
from collections import Counter
from typing import Iterable

STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "into", "after", "over", "under", "today",
    "latest", "live", "news", "update", "updates", "india", "indian", "will", "what", "when", "where",
    "why", "how", "about", "amid", "says", "said", "new", "old", "now", "are", "was", "were", "been",
    "have", "has", "had", "not", "you", "your", "their", "they", "his", "her", "its", "our", "out", "all",
    "more", "less", "than", "then", "also", "first", "last", "top", "big", "watch", "video",
    "report", "reports", "reported", "story", "stories", "article", "articles", "read", "full",
}

# Source/publication names that should not become editorial keywords.
SOURCE_NOISE = {
    "ani", "afp", "ap", "pti", "reuters", "bloomberg", "bbc", "cnn", "nbc", "cnbc", "ndtv",
    "espn", "espncricinfo", "hindustan", "toi", "times", "express", "indianexpress",
    "livemint", "mint", "businessline", "thehindu", "hindu", "news18", "zeenews", "zee",
    "firstpost", "deccan", "herald", "tribune", "wire", "agency", "source", "google", "yahoo",
    "msn", "ht", "abp", "aajtak", "indiatoday", "wion", "moneycontrol", "economictimes",
}

# HTML/CSS/RSS junk that appears in Google News RSS summaries.
MARKUP_NOISE = {
    "nbsp", "nbps", "amp", "quot", "apos", "lt", "gt",
    "href", "target", "blank", "_blank", "rel", "noopener", "noreferrer",
    "font", "color", "style", "class", "span", "div", "img", "src", "alt",
    "width", "height", "border", "align", "valign", "table", "tbody", "tr", "td",
    "br", "p", "a", "b", "i", "strong", "em", "ul", "ol", "li",
    "http", "https", "www", "com", "html", "htm", "rss", "xml",
    "data", "image", "thumbnail", "static", "cdn", "utm", "ref",
    "font-size", "font-family", "background", "ffffff", "000000",
}

DESK_KEYWORDS = {
    "Politics": {
        "modi", "rahul", "gandhi", "bjp", "congress", "election", "parliament",
        "minister", "govt", "government", "cm", "pm"
    },
    "World": {
        "iran", "israel", "usa", "america", "russia", "china", "pakistan", "ukraine",
        "gaza", "trump", "war", "global", "white house", "vance"
    },
    "Business": {
        "sensex", "nifty", "stock", "market", "rbi", "rupee", "gold", "bank",
        "economy", "ipo", "gst"
    },
    "Sports": {
        "cricket", "ipl", "icc", "bcci", "kohli", "rohit", "football", "match",
        "world cup", "test", "odi", "t20"
    },
    "Entertainment": {
        "bollywood", "actor", "actress", "film", "movie", "ott", "trailer",
        "box office", "celebrity"
    },
    "Technology": {
        "ai", "iphone", "google", "openai", "meta", "tesla", "tech", "startup", "app"
    },
    "Health": {
        "health", "covid", "doctor", "hospital", "disease", "medicine", "pregnancy", "vaccine"
    },
    "Education": {
        "neet", "jee", "exam", "nta", "counselling", "counseling", "result",
        "admit card", "school", "college"
    },
    "Crime": {
        "murder", "arrest", "police", "crime", "fir", "court", "accused", "case"
    },
    "Lifestyle": {
        "weather", "rain", "monsoon", "travel", "food", "astrology", "horoscope", "fashion"
    },
}


def clean_html_text(text: str | None) -> str:
    """
    Convert RSS/HTML snippets into clean plain text.

    This prevents tokens like:
    nbsp, href, target, blank, font, color
    from entering clustering, keywords, entities, and desk inference.
    """
    if not text:
        return ""

    value = str(text)

    # Decode escaped HTML first:
    # &lt;font color=&quot;...&quot;&gt; -> <font color="...">
    # &nbsp; -> non-breaking space
    value = html.unescape(value)
    value = value.replace("\xa0", " ")

    # Remove script/style blocks defensively.
    value = re.sub(r"(?is)<script.*?>.*?</script>", " ", value)
    value = re.sub(r"(?is)<style.*?>.*?</style>", " ", value)

    # Remove HTML tags and whatever attributes they contain.
    value = re.sub(r"(?s)<[^>]+>", " ", value)

    # Decode again in case entities appeared after tag removal.
    value = html.unescape(value)
    value = value.replace("\xa0", " ")

    # Remove URLs.
    value = re.sub(r"https?://\S+", " ", value)
    value = re.sub(r"www\.\S+", " ", value)

    # Remove common leftover HTML attribute patterns if malformed markup leaked.
    value = re.sub(r"\b(?:href|src|target|rel|style|class|color|width|height|alt)\s*=\s*['\"][^'\"]*['\"]", " ", value, flags=re.I)
    value = re.sub(r"\b(?:href|src|target|rel|style|class|color|width|height|alt)\s*=\s*\S+", " ", value, flags=re.I)

    # Normalize whitespace.
    value = re.sub(r"\s+", " ", value).strip()
    return value


def normalize_text(text: str) -> str:
    text = clean_html_text(text).lower()

    # Convert separators to spaces before stripping punctuation.
    text = text.replace("_", " ")
    text = text.replace("-", " ")

    # Remove anything not alphanumeric/space.
    text = re.sub(r"[^a-z0-9\s]", " ", text)

    # Remove isolated hex color-looking words/numbers.
    text = re.sub(r"\b[0-9a-f]{6}\b", " ", text)

    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_good_token(token: str) -> bool:
    if not token:
        return False

    token = token.strip().lower()

    if len(token) <= 2:
        return False

    if token in STOPWORDS:
        return False

    if token in SOURCE_NOISE:
        return False

    if token in MARKUP_NOISE:
        return False

    # Reject numeric-only tokens.
    if token.isdigit():
        return False

    # Reject hex colors and CSS-like fragments.
    if re.fullmatch(r"[0-9a-f]{6}", token):
        return False

    # Reject mostly numeric tokens.
    numeric_chars = sum(ch.isdigit() for ch in token)
    if numeric_chars and numeric_chars / max(len(token), 1) > 0.5:
        return False

    # Reject obvious tracking/URL fragments.
    if token.startswith(("utm", "http", "www")):
        return False

    return True


def tokenize(text: str) -> list[str]:
    return [t for t in normalize_text(text).split() if is_good_token(t)]


def top_keywords(texts: Iterable[str], n: int = 12) -> list[str]:
    counts = Counter()

    for text in texts:
        counts.update(tokenize(text))

    return [word for word, _ in counts.most_common(n)]


def extract_entities(text: str, max_entities: int = 12) -> list[str]:
    cleaned = clean_html_text(text)

    if not cleaned:
        return []

    # Conservative: capture title-case names/acronyms and known high-signal tokens.
    title_entities = re.findall(
        r"\b(?:[A-Z][a-z]+|[A-Z]{2,})(?:\s+(?:[A-Z][a-z]+|[A-Z]{2,}))*\b",
        cleaned,
    )
    acronym_entities = re.findall(r"\b[A-Z]{2,}\b", cleaned)

    known = []
    low = normalize_text(cleaned)

    for desk_terms in DESK_KEYWORDS.values():
        for term in desk_terms:
            if term in low and term not in known:
                known.append(term.title())

    merged = []

    for ent in acronym_entities + title_entities + known:
        ent = clean_html_text(ent).strip()

        if len(ent) < 3:
            continue

        normalized_ent = normalize_text(ent)
        collapsed_ent = normalized_ent.replace(" ", "")

        if not normalized_ent:
            continue

        if normalized_ent in STOPWORDS or collapsed_ent in SOURCE_NOISE or collapsed_ent in MARKUP_NOISE:
            continue

        # Avoid single-word publication/source names as entities.
        if normalized_ent in SOURCE_NOISE:
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
            normalized_term = normalize_text(term)
            if normalized_term and normalized_term in low:
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