from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, Iterable, TypeVar

T = TypeVar("T")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL DEFAULT 'rss',
    url TEXT,
    credibility_tier TEXT NOT NULL DEFAULT 'standard',
    active INTEGER NOT NULL DEFAULT 1,
    last_fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS raw_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    source_tier TEXT NOT NULL DEFAULT 'standard',
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    summary TEXT,
    published_at TEXT,
    fetched_at TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    desk_hint TEXT
);

CREATE TABLE IF NOT EXISTS topic_clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    summary TEXT,
    primary_desk TEXT NOT NULL DEFAULT 'National',
    entities TEXT,
    keywords TEXT,
    latest_published_at TEXT,
    item_count INTEGER NOT NULL DEFAULT 0,
    source_count INTEGER NOT NULL DEFAULT 0,
    freshness_score REAL NOT NULL DEFAULT 0,
    source_score REAL NOT NULL DEFAULT 0,
    momentum_score REAL NOT NULL DEFAULT 0,
    archive_score REAL NOT NULL DEFAULT 0,
    opportunity_score REAL NOT NULL DEFAULT 0,
    confidence_level TEXT NOT NULL DEFAULT 'Watch',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cluster_items (
    cluster_id INTEGER NOT NULL,
    raw_item_id INTEGER NOT NULL,
    PRIMARY KEY(cluster_id, raw_item_id),
    FOREIGN KEY(cluster_id) REFERENCES topic_clusters(id),
    FOREIGN KEY(raw_item_id) REFERENCES raw_items(id)
);

CREATE TABLE IF NOT EXISTS archive_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT,
    title TEXT NOT NULL,
    description TEXT,
    transcript TEXT,
    url TEXT,
    tags TEXT,
    published_at TEXT,
    performance_note TEXT,
    content_hash TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS archive_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id INTEGER NOT NULL,
    archive_asset_id INTEGER NOT NULL,
    relevance_score REAL NOT NULL,
    match_reason TEXT,
    recommended_use TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(cluster_id, archive_asset_id),
    FOREIGN KEY(cluster_id) REFERENCES topic_clusters(id),
    FOREIGN KEY(archive_asset_id) REFERENCES archive_assets(id)
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id INTEGER NOT NULL,
    user_label TEXT,
    rating TEXT NOT NULL,
    comment TEXT,
    action_taken TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(cluster_id) REFERENCES topic_clusters(id)
);

CREATE TABLE IF NOT EXISTS digest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    digest_title TEXT NOT NULL,
    digest_text TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'email_draft',
    created_at TEXT NOT NULL
);
"""


def _retry_locked(fn: Callable[[], T], attempts: int = 6) -> T:
    """Retry briefly when SQLite is locked by another Streamlit rerun/session."""
    delay = 0.2
    last_exc: sqlite3.OperationalError | None = None

    for _ in range(attempts):
        try:
            return fn()
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower():
                raise
            last_exc = exc
            time.sleep(delay)
            delay *= 1.6

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("SQLite retry failed without captured exception")


def connect(db_path: str | Path = "editorial_radar.db") -> sqlite3.Connection:
    path = Path(db_path)
    if path.parent and str(path.parent) not in {"", "."}:
        path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        str(path),
        timeout=30.0,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row

    # Make SQLite more tolerant of Streamlit reruns/concurrent sessions.
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")

    return conn


def init_db(conn: sqlite3.Connection) -> None:
    def _run() -> None:
        conn.executescript(SCHEMA)
        conn.commit()

    _retry_locked(_run)


def rows(conn: sqlite3.Connection, query: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    def _run() -> list[dict[str, Any]]:
        cur = conn.execute(query, tuple(params))
        return [dict(r) for r in cur.fetchall()]

    return _retry_locked(_run)


def one(conn: sqlite3.Connection, query: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
    def _run() -> dict[str, Any] | None:
        cur = conn.execute(query, tuple(params))
        r = cur.fetchone()
        return dict(r) if r else None

    return _retry_locked(_run)


def execute(conn: sqlite3.Connection, query: str, params: Iterable[Any] = ()) -> int:
    def _run() -> int:
        cur = conn.execute(query, tuple(params))
        conn.commit()
        return int(cur.lastrowid or 0)

    return _retry_locked(_run)


def upsert_source(
    conn: sqlite3.Connection,
    name: str,
    type_: str = "rss",
    url: str | None = None,
    credibility_tier: str = "standard",
    active: bool = True,
) -> None:
    def _run() -> None:
        conn.execute(
            """
            INSERT INTO sources(name, type, url, credibility_tier, active)
            VALUES(?,?,?,?,?)
            ON CONFLICT(name) DO UPDATE SET
              type=excluded.type,
              url=excluded.url,
              credibility_tier=excluded.credibility_tier,
              active=excluded.active
            """,
            (name, type_, url, credibility_tier, 1 if active else 0),
        )
        conn.commit()

    _retry_locked(_run)
