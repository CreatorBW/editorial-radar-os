from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .db import rows
from .nlp import tokenize
from .scoring import opportunity_score, utcnow_iso


def _hash(*parts: str | None) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update((p or "").strip().lower().encode("utf-8"))
        h.update(b"|")
    return h.hexdigest()


def import_archive_csv(conn: sqlite3.Connection, csv_path: str | Path) -> int:
    path = Path(csv_path)
    inserted = 0
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = (row.get("title") or row.get("Title") or "").strip()
            if not title:
                continue
            video_id = row.get("video_id") or row.get("Video ID") or row.get("id") or ""
            description = row.get("description") or row.get("Description") or ""
            transcript = row.get("transcript") or row.get("Transcript") or ""
            url = row.get("url") or row.get("URL") or ""
            tags = row.get("tags") or row.get("Tags") or ""
            published_at = row.get("published_at") or row.get("Published At") or ""
            content_hash = _hash(video_id, title, url)
            try:
                conn.execute(
                    """
                    INSERT INTO archive_assets(video_id, title, description, transcript, url, tags, published_at, performance_note, content_hash)
                    VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (video_id, title, description, transcript, url, tags, published_at, row.get("performance_note") or "", content_hash),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                pass
    conn.commit()
    return inserted


def rebuild_archive_matches(conn: sqlite3.Connection, min_score: float = 18.0, limit_per_cluster: int = 8) -> int:
    conn.execute("DELETE FROM archive_matches")
    clusters = rows(conn, "SELECT * FROM topic_clusters")
    assets = rows(conn, "SELECT * FROM archive_assets")
    inserted = 0
    now = utcnow_iso()
    for cl in clusters:
        cl_text = " ".join([cl.get("title") or "", cl.get("summary") or "", " ".join(json.loads(cl.get("keywords") or "[]")), " ".join(json.loads(cl.get("entities") or "[]"))])
        cl_tokens = set(tokenize(cl_text))
        scored = []
        for asset in assets:
            asset_text = " ".join([asset.get("title") or "", asset.get("description") or "", asset.get("transcript") or "", asset.get("tags") or ""])
            asset_tokens = set(tokenize(asset_text))
            if not cl_tokens or not asset_tokens:
                continue
            overlap = cl_tokens & asset_tokens
            score = round((len(overlap) / max(len(cl_tokens), 1)) * 100, 2)
            if score >= min_score:
                reason = "Matched terms: " + ", ".join(sorted(list(overlap))[:10])
                scored.append((score, asset, reason))
        scored.sort(key=lambda x: x[0], reverse=True)
        max_score = 0.0
        for score, asset, reason in scored[:limit_per_cluster]:
            max_score = max(max_score, score)
            conn.execute(
                """
                INSERT OR IGNORE INTO archive_matches(cluster_id, archive_asset_id, relevance_score, match_reason, recommended_use, created_at)
                VALUES(?,?,?,?,?,?)
                """,
                (cl["id"], asset["id"], score, reason, _recommended_use(cl, asset), now),
            )
            inserted += 1
        if max_score:
            new_opp = opportunity_score(cl["freshness_score"], cl["source_score"], cl["momentum_score"], min(max_score, 100))
            conn.execute(
                "UPDATE topic_clusters SET archive_score=?, opportunity_score=?, updated_at=? WHERE id=?",
                (min(max_score, 100), new_opp, now, cl["id"]),
            )
    conn.commit()
    return inserted


def _recommended_use(cluster: dict, asset: dict) -> str:
    desk = cluster.get("primary_desk") or "National"
    if desk == "Archive":
        return "Republish as archive explainer with updated context."
    return "Use as background clip/reference for explainer, timeline, or contextual video package."
