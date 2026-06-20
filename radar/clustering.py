from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter

from .db import rows
from .nlp import extract_entities, headline_from_keywords, infer_desk, jaccard, tokenize, top_keywords
from .scoring import confidence_label, freshness_score, momentum_score, opportunity_score, source_score, utcnow_iso


def clean_news_title(title: str) -> str:
    """Remove common Google News source suffixes from titles.

    Example: "Story headline - Reuters" -> "Story headline".
    This prevents source names from becoming keywords/entities.
    """
    title = title or ""
    # Split only when suffix looks like a news source, not when the headline itself uses hyphen.
    parts = re.split(r"\s+-\s+", title)
    if len(parts) >= 2 and len(parts[-1].split()) <= 4:
        return " - ".join(parts[:-1]).strip()
    return title.strip()


def _cluster_signature(item: dict) -> set[str]:
    title = clean_news_title(item["title"])
    return set(tokenize(f"{title} {item.get('summary') or ''}"))


def _entity_set(item: dict) -> set[str]:
    text = f"{clean_news_title(item['title'])} {item.get('summary') or ''}"
    return {e.lower() for e in extract_entities(text, 8)}


def _compatible_desk(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return True
    if a == b:
        return True
    # National can mix with desks, but Sports/Entertainment/Business should not merge casually.
    return "National" in {a, b}


def _can_join_cluster(item: dict, sig: set[str], ents: set[str], cluster: dict) -> tuple[bool, float]:
    if not _compatible_desk(item.get("desk_hint"), cluster.get("desk")):
        return False, 0.0
    core_tokens = cluster["core_tokens"]
    token_overlap = sig & core_tokens
    entity_overlap = ents & cluster["entities"]
    score = jaccard(sig, core_tokens)

    # Strict enough to avoid topic contamination.
    # Either strong token overlap, or at least entity overlap plus some token overlap.
    if len(token_overlap) >= 3 and score >= 0.22:
        return True, score
    if len(entity_overlap) >= 1 and len(token_overlap) >= 2 and score >= 0.14:
        return True, score
    return False, score


def _clear_rebuild_tables(conn: sqlite3.Connection) -> None:
    """Clear derived cluster tables in FK-safe order.

    Why feedback is deleted here:
    topic_clusters are rebuilt from scratch on each refresh, so old cluster IDs are no longer stable.
    Keeping feedback attached to old cluster IDs causes FOREIGN KEY failures and stale feedback.
    A later production version should use stable cluster fingerprints instead of autoincrement IDs.
    """
    conn.execute("DELETE FROM feedback")
    conn.execute("DELETE FROM cluster_items")
    conn.execute("DELETE FROM archive_matches")
    conn.execute("DELETE FROM topic_clusters")
    conn.commit()


def rebuild_clusters(conn: sqlite3.Connection, max_items: int = 500) -> int:
    items = rows(
        conn,
        """
        SELECT * FROM raw_items
        ORDER BY COALESCE(published_at, fetched_at) DESC
        LIMIT ?
        """,
        (max_items,),
    )

    _clear_rebuild_tables(conn)

    clusters: list[dict] = []
    for item in items:
        item = dict(item)
        item["clean_title"] = clean_news_title(item["title"])
        sig = _cluster_signature(item)
        ents = _entity_set(item)
        best_idx = None
        best_score = 0.0
        for i, cl in enumerate(clusters):
            can_join, score = _can_join_cluster(item, sig, ents, cl)
            if can_join and score > best_score:
                best_score = score
                best_idx = i
        if best_idx is not None:
            clusters[best_idx]["items"].append(item)
            clusters[best_idx]["all_tokens"].update(sig)
            clusters[best_idx]["entities"].update(ents)
        else:
            clusters.append({
                "items": [item],
                "core_tokens": set(sig),
                "all_tokens": set(sig),
                "entities": set(ents),
                "desk": item.get("desk_hint") or infer_desk(item["title"]),
            })

    now = utcnow_iso()
    for cl in clusters:
        cl_items = cl["items"]
        texts = [f"{i.get('clean_title') or clean_news_title(i['title'])} {i.get('summary') or ''}" for i in cl_items]
        keywords = top_keywords(texts, 12)
        title = _best_cluster_title(cl_items, keywords)
        summary = _cluster_summary(cl_items, keywords)
        entities = extract_entities(" ".join(texts), 12)
        latest = max([i.get("published_at") or i.get("fetched_at") for i in cl_items if i.get("published_at") or i.get("fetched_at")], default=now)
        source_names = [i["source_name"] for i in cl_items]
        source_tiers = [i.get("source_tier", "standard") for i in cl_items]
        desk = _majority([i.get("desk_hint") or infer_desk(i["title"]) for i in cl_items]) or infer_desk(" ".join(texts))
        fresh = freshness_score(latest)
        src_score = source_score(source_tiers)
        momentum = momentum_score(len(cl_items), len(set(source_names)))
        archive = 0.0
        opp = opportunity_score(fresh, src_score, momentum, archive)
        conf = confidence_label(len(cl_items), len(set(source_names)), src_score, fresh)
        cur = conn.execute(
            """
            INSERT INTO topic_clusters(
              title, summary, primary_desk, entities, keywords, latest_published_at,
              item_count, source_count, freshness_score, source_score, momentum_score,
              archive_score, opportunity_score, confidence_level, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                title, summary, desk, json.dumps(entities), json.dumps(keywords), latest,
                len(cl_items), len(set(source_names)), fresh, src_score, momentum,
                archive, opp, conf, now, now,
            ),
        )
        cluster_id = cur.lastrowid
        for item in cl_items:
            conn.execute("INSERT INTO cluster_items(cluster_id, raw_item_id) VALUES(?,?)", (cluster_id, item["id"]))
    conn.commit()
    return len(clusters)


def _majority(values: list[str]) -> str | None:
    if not values:
        return None
    return Counter(values).most_common(1)[0][0]


def _best_cluster_title(items: list[dict], keywords: list[str]) -> str:
    if not items:
        return headline_from_keywords(keywords)
    title = items[0].get("clean_title") or clean_news_title(items[0]["title"])
    return title[:110] or headline_from_keywords(keywords)


def _cluster_summary(items: list[dict], keywords: list[str]) -> str:
    top = ", ".join(keywords[:6]) if keywords else "related terms"
    return f"Detected from {len(items)} recent item(s). Key terms: {top}. Review evidence before publishing."
