from __future__ import annotations

import json
import sqlite3
from textwrap import shorten

from .db import rows
from .scoring import priority_from_score, utcnow_iso


def cluster_detail(conn: sqlite3.Connection, cluster_id: int) -> dict:
    cluster = rows(conn, "SELECT * FROM topic_clusters WHERE id=?", (cluster_id,))
    if not cluster:
        raise ValueError(f"Cluster {cluster_id} not found")
    cl = cluster[0]
    cl["keywords_list"] = json.loads(cl.get("keywords") or "[]")
    cl["entities_list"] = json.loads(cl.get("entities") or "[]")
    cl["items"] = rows(
        conn,
        """
        SELECT r.* FROM raw_items r
        JOIN cluster_items ci ON ci.raw_item_id = r.id
        WHERE ci.cluster_id=?
        ORDER BY COALESCE(r.published_at, r.fetched_at) DESC
        """,
        (cluster_id,),
    )
    cl["archive_matches"] = rows(
        conn,
        """
        SELECT am.*, aa.video_id, aa.title, aa.url, aa.published_at, aa.tags
        FROM archive_matches am
        JOIN archive_assets aa ON aa.id = am.archive_asset_id
        WHERE am.cluster_id=?
        ORDER BY am.relevance_score DESC
        """,
        (cluster_id,),
    )
    return cl


def generate_keywords(topic: str, platform: str = "YouTube") -> dict[str, list[str]]:
    words = [w for w in topic.replace("|", " ").replace("-", " ").split() if len(w) > 2]
    base = " ".join(words[:5]).strip()
    primary = [base] if base else [topic]
    secondary = []
    modifiers = ["latest", "explained", "today", "full timeline", "what happened", "breaking", "update"]
    for m in modifiers:
        if platform.lower() in {"youtube", "shorts"}:
            secondary.append(f"{base} {m}".strip())
        else:
            secondary.append(f"{m} {base}".strip())
    hashtags = ["#" + w.title().replace(" ", "") for w in words[:6]]
    questions = [
        f"What happened in {base}?" if base else f"What happened in {topic}?",
        f"Why is {base} trending?" if base else f"Why is {topic} trending?",
        f"What is the latest update on {base}?" if base else f"What is the latest update on {topic}?",
    ]
    return {
        "primary": primary[:5],
        "secondary": list(dict.fromkeys(secondary))[:12],
        "questions": questions,
        "hashtags": hashtags,
        "avoid": ["Unverified casualty claims", "Unsupported viral claims", "Absolute claims without source evidence"],
    }


def generate_brief(conn: sqlite3.Connection, cluster_id: int) -> str:
    cl = cluster_detail(conn, cluster_id)
    priority = priority_from_score(float(cl["opportunity_score"]), cl["confidence_level"])
    keywords = cl["keywords_list"]
    entities = cl["entities_list"]
    source_lines = []
    for item in cl["items"][:8]:
        source_lines.append(f"- {item['source_name']}: {shorten(item['title'], width=120, placeholder='...')} ({item.get('published_at') or 'no date'})")
    archive_lines = []
    for m in cl["archive_matches"][:5]:
        archive_lines.append(f"- {m['title']} | score {m['relevance_score']} | {m.get('url') or 'no url'}")
    if not archive_lines:
        archive_lines.append("- No strong archive match found yet.")

    keyword_pack = generate_keywords(cl["title"], "YouTube")

    return f"""# Editorial Brief: {cl['title']}

## Priority
{priority} — confidence: {cl['confidence_level']}; opportunity score: {cl['opportunity_score']}

## What we know
{cl['summary']}

## Evidence
- Source count: {cl['source_count']}
- Item count: {cl['item_count']}
- Freshness score: {cl['freshness_score']}
- Source score: {cl['source_score']}
- Momentum score: {cl['momentum_score']}
- Latest source timestamp: {cl.get('latest_published_at') or 'unknown'}

## Key entities
{', '.join(entities) if entities else 'No strong entities detected.'}

## Suggested editorial angle
Use this as a {'breaking update' if priority == 'High' else 'watch/explainer opportunity'} for the {cl['primary_desk']} desk. Keep the copy evidence-led and avoid unsupported claims.

## Suggested YouTube titles
1. {cl['title']}: What Happened And Why It Matters
2. {cl['title']} Explained: Full Timeline And Latest Updates
3. Latest On {cl['title']}: Key Facts So Far

## Suggested keywords
Primary: {', '.join(keyword_pack['primary'])}
Secondary: {', '.join(keyword_pack['secondary'][:8])}
Questions: {', '.join(keyword_pack['questions'])}

## Archive opportunities
{chr(10).join(archive_lines)}

## Source evidence
{chr(10).join(source_lines) if source_lines else '- No sources attached.'}

## Risk notes
- Do not state exact search volume unless the source provides it.
- Treat this as {cl['confidence_level']} based on currently collected evidence.
- Re-check source links before final publication.

Generated at: {utcnow_iso()}
"""


def save_digest(conn: sqlite3.Connection, title: str, text: str, channel: str = "email_draft") -> int:
    cur = conn.execute(
        "INSERT INTO digest_runs(digest_title, digest_text, channel, created_at) VALUES(?,?,?,?)",
        (title, text, channel, utcnow_iso()),
    )
    conn.commit()
    return int(cur.lastrowid)
