from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable
from urllib.parse import quote_plus

from .nlp import infer_desk
from .scoring import utcnow_iso


def content_hash(*parts: str | None) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update((part or "").strip().lower().encode("utf-8"))
        h.update(b"|")
    return h.hexdigest()


def normalize_published(value: str | None) -> str | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except Exception:
            return None


def google_news_rss_url(query: str | None = None, country: str = "IN", language: str = "en", hours: int = 6) -> str:
    # Google News RSS is treated as a feed source, not an official guaranteed trends API.
    hl = f"{language}-{country}"
    ceid = f"{country}:{language}"
    if query:
        q = quote_plus(f"{query} when:{hours}h")
        return f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={country}&ceid={ceid}"
    return f"https://news.google.com/rss?hl={hl}&gl={country}&ceid={ceid}"


def fetch_rss(url: str, source_name: str, source_tier: str = "standard", timeout: int = 20) -> list[dict]:
    try:
        import feedparser  # type: ignore
        import requests  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Missing dependencies. Run: pip install -r requirements.txt") from exc

    resp = requests.get(url, timeout=timeout, headers={"User-Agent": "EditorialRadarOS/1.0"})
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    fetched_at = utcnow_iso()
    out = []
    for entry in feed.entries:
        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "").strip()
        summary = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
        published_raw = getattr(entry, "published", None) or getattr(entry, "updated", None)
        published_at = normalize_published(published_raw) or fetched_at
        if not title or not link:
            continue
        out.append({
            "source_name": source_name,
            "source_tier": source_tier,
            "title": title,
            "url": link,
            "summary": summary,
            "published_at": published_at,
            "fetched_at": fetched_at,
            "content_hash": content_hash(title, link),
            "desk_hint": infer_desk(f"{title} {summary}"),
        })
    return out


def insert_raw_items(conn: sqlite3.Connection, items: Iterable[dict]) -> int:
    inserted = 0
    for item in items:
        try:
            conn.execute(
                """
                INSERT INTO raw_items(source_name, source_tier, title, url, summary, published_at, fetched_at, content_hash, desk_hint)
                VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    item["source_name"], item.get("source_tier", "standard"), item["title"], item["url"],
                    item.get("summary"), item.get("published_at"), item.get("fetched_at", utcnow_iso()),
                    item.get("content_hash") or content_hash(item["title"], item["url"]), item.get("desk_hint")
                ),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    return inserted
