from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
PRAGMA journal_mode=WAL;

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


def connect(db_path: str | Path = "editorial_radar.db") -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def rows(conn: sqlite3.Connection, query: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    cur = conn.execute(query, tuple(params))
    return [dict(r) for r in cur.fetchall()]


def one(conn: sqlite3.Connection, query: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
    cur = conn.execute(query, tuple(params))
    r = cur.fetchone()
    return dict(r) if r else None


def execute(conn: sqlite3.Connection, query: str, params: Iterable[Any] = ()) -> int:
    cur = conn.execute(query, tuple(params))
    conn.commit()
    return int(cur.lastrowid or 0)


def upsert_source(conn: sqlite3.Connection, name: str, type_: str = "rss", url: str | None = None,
                  credibility_tier: str = "standard", active: bool = True) -> None:
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
