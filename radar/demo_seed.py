from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from .collectors import content_hash, insert_raw_items
from .db import upsert_source
from .scoring import utcnow_iso


def seed_demo(conn: sqlite3.Connection) -> None:
    upsert_source(conn, "Google News India", "rss", "demo", "standard", True)
    upsert_source(conn, "Trusted Wire", "rss", "demo", "trusted", True)
    upsert_source(conn, "Official Update", "rss", "demo", "official", True)
    now = datetime.now(timezone.utc)
    items = [
        ("Google News India", "standard", "NEET Counselling 2026 Update: NTA Expected To Release Schedule Soon", "Education desk tracks NEET counselling, NTA updates and student queries.", "Education"),
        ("Trusted Wire", "trusted", "NEET UG Counselling Latest: Students Await Official NTA Notification", "Multiple reports say students are looking for official counselling updates.", "Education"),
        ("Official Update", "official", "Education Ministry Reviews NEET Counselling Preparedness", "Officials discussed examination and counselling readiness.", "Education"),
        ("Google News India", "standard", "Delhi Rain Alert: IMD Predicts Heavy Showers In NCR", "Rain, traffic and waterlogging updates in Delhi NCR.", "Lifestyle"),
        ("Trusted Wire", "trusted", "Heavy Rain In Delhi NCR Causes Traffic Slowdown", "Waterlogging and traffic advisories are being monitored.", "Lifestyle"),
        ("Google News India", "standard", "Iran Israel Conflict: Global Leaders Urge Restraint", "World desk monitors West Asia conflict and India impact.", "World"),
        ("Trusted Wire", "trusted", "Middle East Tensions Rise Amid Iran Israel Conflict", "Fresh diplomatic activity follows escalation in the region.", "World"),
        ("Google News India", "standard", "Sensex Nifty Today: Markets Open Lower Amid Global Cues", "Market action, RBI, banking and global cues.", "Business"),
        ("Google News India", "standard", "India Cricket Squad Update: Selection Buzz Before Big Series", "Cricket fans await team selection and injury updates.", "Sports"),
        ("Trusted Wire", "trusted", "Bollywood Actor Announces New OTT Release", "Entertainment desk tracks OTT launches and celebrity interviews.", "Entertainment"),
    ]
    out = []
    for idx, (source, tier, title, summary, desk) in enumerate(items):
        published = (now - timedelta(minutes=idx * 22)).isoformat()
        out.append({
            "source_name": source,
            "source_tier": tier,
            "title": title,
            "url": f"https://example.com/demo/{idx}",
            "summary": summary,
            "published_at": published,
            "fetched_at": utcnow_iso(),
            "content_hash": content_hash(title, f"https://example.com/demo/{idx}"),
            "desk_hint": desk,
        })
    insert_raw_items(conn, out)

    archive_rows = [
        ("vid001", "NEET Paper Leak Row Explained: Full Timeline", "Archive debate and explainer on NEET controversy", "NEET NTA counselling paper leak Supreme Court student protest", "https://youtube.com/watch?v=demo1", "NEET,NTA,Education", "2024-07-01"),
        ("vid002", "Delhi Floods And Monsoon Chaos: Ground Report", "Delhi NCR rain waterlogging traffic monsoon", "Delhi rain IMD alert NCR waterlogging traffic", "https://youtube.com/watch?v=demo2", "Delhi,Rain,IMD", "2023-08-15"),
        ("vid003", "Iran Israel Conflict Explained By Experts", "West Asia geopolitics, Iran, Israel, global security", "Iran Israel conflict Middle East tensions Netanyahu Tehran", "https://youtube.com/watch?v=demo3", "Iran,Israel,World", "2024-04-20"),
        ("vid004", "Sensex Nifty Crash: Market Experts Explain Global Cues", "Market fall, Sensex, Nifty, RBI, global markets", "Sensex Nifty market RBI rupee stock exchange", "https://youtube.com/watch?v=demo4", "Markets,Business", "2025-01-10"),
        ("vid005", "India Cricket Squad Selection Debate", "Cricket team selection, BCCI, player injury updates", "India cricket squad BCCI selection Rohit Kohli", "https://youtube.com/watch?v=demo5", "Cricket,Sports", "2025-03-01"),
    ]
    for row in archive_rows:
        video_id, title, desc, transcript, url, tags, published = row
        try:
            conn.execute(
                """
                INSERT INTO archive_assets(video_id, title, description, transcript, url, tags, published_at, performance_note, content_hash)
                VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (video_id, title, desc, transcript, url, tags, published, "Demo asset", content_hash(video_id, title, url)),
            )
        except sqlite3.IntegrityError:
            pass
    conn.commit()
