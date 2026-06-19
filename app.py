from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from textwrap import shorten

import pandas as pd
import streamlit as st

from radar.archive import import_archive_csv, rebuild_archive_matches
from radar.briefs import cluster_detail, generate_brief, generate_keywords, save_digest
from radar.clustering import rebuild_clusters
from radar.collectors import fetch_rss, google_news_rss_url, insert_raw_items
from radar.config import APP_NAME, DEFAULT_DB_PATH, DESKS, EDITORIAL_RULES, PLATFORMS
from radar.db import connect, init_db, rows, upsert_source
from radar.demo_seed import seed_demo
from radar.scoring import priority_from_score, utcnow_iso

st.set_page_config(page_title=APP_NAME, page_icon="📰", layout="wide")

DB_PATH = os.environ.get("EDITORIAL_RADAR_DB", DEFAULT_DB_PATH)


def get_conn():
    conn = connect(DB_PATH)
    init_db(conn)
    return conn


conn = get_conn()

DEFAULT_EDITORIAL_QUERIES = [
    None,
    "India politics",
    "NEET counselling",
    "Delhi rain",
    "Iran Israel",
    "Sensex Nifty",
    "India cricket squad",
    "Bollywood OTT",
]


def refresh_radar_one_click() -> dict:
    """One-button editorial refresh. Keeps editors away from Admin mechanics."""
    fetched_total = 0
    inserted_total = 0
    errors: list[str] = []
    for query in DEFAULT_EDITORIAL_QUERIES:
        url = google_news_rss_url(query, country="IN", language="en", hours=6)
        source_name = "Google News India" if not query else f"Google News · {query}"
        try:
            items = fetch_rss(url, source_name=source_name, source_tier="standard")
            fetched_total += len(items)
            inserted_total += insert_raw_items(conn, items)
            upsert_source(conn, source_name, "rss", url, "standard", True)
        except Exception as exc:
            errors.append(f"{source_name}: {exc}")
    clusters = rebuild_clusters(conn)
    matches = rebuild_archive_matches(conn)
    return {
        "fetched": fetched_total,
        "inserted": inserted_total,
        "clusters": clusters,
        "matches": matches,
        "errors": errors,
    }


def render_editor_refresh_bar() -> None:
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        st.caption("One-click update for editors: fetch latest signals, rebuild topics, refresh archive matches.")
    with c2:
        if st.button("Refresh Radar", type="primary", use_container_width=True):
            with st.spinner("Refreshing latest editorial signals..."):
                result = refresh_radar_one_click()
            if result["errors"]:
                st.warning(f"Refresh completed with {len(result['errors'])} source error(s). Open Advanced for details.")
                st.session_state["last_refresh_errors"] = result["errors"]
            st.success(
                f"Updated: {result['inserted']} new item(s), {result['clusters']} topic(s), "
                f"{result['matches']} archive match(es)."
            )
            st.rerun()
    with c3:
        if st.button("Load Demo", use_container_width=True):
            seed_demo(conn)
            clusters = rebuild_clusters(conn)
            matches = rebuild_archive_matches(conn)
            st.success(f"Demo loaded: {clusters} topics, {matches} archive matches.")
            st.rerun()


def safe_json_list(value: str | None) -> list[str]:
    try:
        return json.loads(value or "[]")
    except Exception:
        return []


def priority_badge(score: float, confidence: str) -> str:
    return priority_from_score(score, confidence)


def load_clusters(desk: str = "All", confidence: str = "All", min_score: float = 0) -> list[dict]:
    query = "SELECT * FROM topic_clusters WHERE opportunity_score >= ?"
    params: list = [min_score]
    if desk != "All":
        query += " AND primary_desk = ?"
        params.append(desk)
    if confidence != "All":
        query += " AND confidence_level = ?"
        params.append(confidence)
    query += " ORDER BY opportunity_score DESC, latest_published_at DESC"
    return rows(conn, query, params)


def render_cluster_card(cl: dict, compact: bool = False) -> None:
    priority = priority_badge(float(cl["opportunity_score"]), cl["confidence_level"])
    with st.container(border=True):
        top_cols = st.columns([5, 1, 1, 1])
        with top_cols[0]:
            st.markdown(f"### {cl['title']}")
            st.caption(f"Desk: {cl['primary_desk']} · Latest: {cl.get('latest_published_at') or 'unknown'}")
        with top_cols[1]:
            st.metric("Priority", priority)
        with top_cols[2]:
            st.metric("Confidence", cl["confidence_level"])
        with top_cols[3]:
            st.metric("Score", f"{float(cl['opportunity_score']):.1f}")

        st.write(cl.get("summary") or "No summary.")
        kw = safe_json_list(cl.get("keywords"))[:8]
        ents = safe_json_list(cl.get("entities"))[:8]
        if kw:
            st.caption("Keywords: " + ", ".join(kw))
        if ents:
            st.caption("Entities: " + ", ".join(ents))

        if compact:
            return

        a, b, c, d = st.columns(4)
        a.metric("Sources", cl["source_count"])
        b.metric("Items", cl["item_count"])
        c.metric("Freshness", f"{float(cl['freshness_score']):.0f}")
        d.metric("Archive", f"{float(cl['archive_score']):.0f}")

        with st.expander("Why am I seeing this? Evidence and limitations", expanded=False):
            render_evidence(int(cl["id"]))

        action_cols = st.columns(5)
        if action_cols[0].button("Open brief", key=f"brief_{cl['id']}"):
            st.session_state["selected_cluster_id"] = int(cl["id"])
            st.session_state["page"] = "Brief Builder"
            st.rerun()
        if action_cols[1].button("Archive matches", key=f"archive_{cl['id']}"):
            st.session_state["selected_cluster_id"] = int(cl["id"])
            st.session_state["page"] = "Archive Matches"
            st.rerun()
        if action_cols[2].button("Keywords", key=f"keywords_{cl['id']}"):
            st.session_state["selected_topic"] = cl["title"]
            st.session_state["page"] = "Keyword Lab"
            st.rerun()
        with action_cols[3]:
            if st.button("Useful", key=f"useful_{cl['id']}"):
                conn.execute(
                    "INSERT INTO feedback(cluster_id, rating, comment, created_at) VALUES(?,?,?,?)",
                    (cl["id"], "useful", "Marked from card", utcnow_iso()),
                )
                conn.commit()
                st.success("Feedback saved")
        with action_cols[4]:
            if st.button("Watch", key=f"watch_{cl['id']}"):
                conn.execute(
                    "INSERT INTO feedback(cluster_id, rating, comment, action_taken, created_at) VALUES(?,?,?,?,?)",
                    (cl["id"], "watch", "Added to watchlist concept", "watch", utcnow_iso()),
                )
                conn.commit()
                st.info("Marked as watch")


def render_evidence(cluster_id: int) -> None:
    cl = cluster_detail(conn, cluster_id)
    st.markdown("#### Signal")
    st.write(
        f"This topic appears because {cl['item_count']} item(s) from {cl['source_count']} source(s) were clustered together. "
        f"Confidence is **{cl['confidence_level']}**."
    )
    st.markdown("#### Scores")
    score_df = pd.DataFrame([
        {"Metric": "Freshness", "Value": cl["freshness_score"], "Meaning": "How recent the latest item is"},
        {"Metric": "Source", "Value": cl["source_score"], "Meaning": "Credibility and tier of sources"},
        {"Metric": "Momentum", "Value": cl["momentum_score"], "Meaning": "Item/source count proxy, not search volume"},
        {"Metric": "Archive", "Value": cl["archive_score"], "Meaning": "Strength of archive matches"},
        {"Metric": "Opportunity", "Value": cl["opportunity_score"], "Meaning": "Combined publishing opportunity"},
    ])
    st.dataframe(score_df, use_container_width=True, hide_index=True)
    st.markdown("#### Source evidence")
    if cl["items"]:
        src_df = pd.DataFrame([{
            "Source": i["source_name"],
            "Tier": i["source_tier"],
            "Title": i["title"],
            "Published": i.get("published_at"),
            "URL": i["url"],
        } for i in cl["items"]])
        st.dataframe(src_df, use_container_width=True, hide_index=True)
    else:
        st.warning("No source items are attached to this cluster.")
    st.markdown("#### Limitations")
    st.info(
        "Momentum is computed from collected item/source count. It is not exact search volume. "
        "Editors should verify source links before final publication."
    )


def sidebar() -> str:
    with st.sidebar:
        st.title(APP_NAME)
        st.caption("For editors: open, refresh, act. No system routing required.")
        pages = [
            "Today’s Radar",
            "Ask Radar",
            "Story Queue",
            "Archive",
            "Keyword Lab",
            "Briefs",
            "Advanced",
        ]
        default_page = st.session_state.get("page", "Today’s Radar")
        page = st.radio("Workspace", pages, index=pages.index(default_page) if default_page in pages else 0)
        st.session_state["page"] = page
        st.divider()
        st.markdown("#### Trust rules")
        for rule in EDITORIAL_RULES[:4]:
            st.caption(f"• {rule}")
        st.divider()
        with st.expander("Advanced system tools", expanded=False):
            if st.button("Seed demo data"):
                seed_demo(conn)
                clusters = rebuild_clusters(conn)
                matches = rebuild_archive_matches(conn)
                st.success(f"Demo seeded. Clusters: {clusters}; archive matches: {matches}")
                st.rerun()
            if st.button("Rebuild clusters + archive matches"):
                clusters = rebuild_clusters(conn)
                matches = rebuild_archive_matches(conn)
                st.success(f"Rebuilt {clusters} clusters and {matches} archive matches")
                st.rerun()
            if st.session_state.get("last_refresh_errors"):
                st.caption("Last refresh errors")
                for err in st.session_state["last_refresh_errors"][:5]:
                    st.caption(f"• {err}")
    return page

def page_radar() -> None:
    st.title("Today’s Radar")
    st.caption("One screen for editors: refresh latest signals, review trusted opportunities, open evidence, act.")
    render_editor_refresh_bar()
    st.divider()

    clusters = load_clusters(min_score=0)
    if not clusters:
        st.info("No data yet. Click **Refresh Radar** for live sources or **Load Demo** to preview the workflow.")
        return

    high = [c for c in clusters if priority_badge(float(c["opportunity_score"]), c["confidence_level"]) == "High"]
    watch = [c for c in clusters if c["confidence_level"] in {"Watch", "Weak"}]
    archive = [c for c in clusters if float(c["archive_score"]) > 0]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Topics", len(clusters))
    k2.metric("High Priority", len(high))
    k3.metric("Archive Ready", len(archive))
    k4.metric("Watch", len(watch))

    tab1, tab2, tab3, tab4 = st.tabs(["Best Now", "Archive Ready", "Needs Watch", "All Topics"])
    with tab1:
        st.subheader("Best opportunities now")
        for cl in clusters[:6]:
            render_cluster_card(cl)
    with tab2:
        st.subheader("Topics with archive matches")
        if not archive:
            st.info("No archive matches yet. Upload archive CSV from Archive or load demo.")
        for cl in archive[:8]:
            render_cluster_card(cl)
    with tab3:
        st.subheader("Developing / weak signals")
        if not watch:
            st.success("No weak watch items currently shown.")
        for cl in watch[:8]:
            render_cluster_card(cl)
    with tab4:
        for cl in clusters[:20]:
            render_cluster_card(cl, compact=True)


def page_intent_search() -> None:
    st.title("Ask Radar")
    render_editor_refresh_bar()
    st.caption("Ask in plain English. The app converts intent into source-backed editorial cards.")
    q = st.text_input("Ask Editorial Radar", placeholder="Example: What should the archive desk publish today?")
    desk = st.selectbox("Desk filter", ["All"] + DESKS)
    if not q:
        st.info("Try: 'Find archive opportunities for today', 'Give me keywords for NEET', or 'Validate Iran Israel conflict'.")
        return
    q_low = q.lower()
    min_archive = "archive" in q_low or "old video" in q_low or "republish" in q_low
    wants_keywords = "keyword" in q_low or "seo" in q_low or "youtube" in q_low or "tag" in q_low
    wants_validate = "validate" in q_low or "real" in q_low or "trust" in q_low or "verify" in q_low

    clusters = load_clusters(desk=desk, min_score=0)
    tokens = set(q_low.replace("?", "").split())
    ranked = []
    for cl in clusters:
        hay = " ".join([cl["title"], cl.get("summary") or "", " ".join(safe_json_list(cl.get("keywords"))) ]).lower()
        overlap = len(tokens & set(hay.split()))
        score = float(cl["opportunity_score"]) + overlap * 12
        if min_archive:
            score += float(cl["archive_score"]) * 2
        ranked.append((score, cl))
    ranked.sort(key=lambda x: x[0], reverse=True)
    results = [cl for _, cl in ranked[:6]]

    st.markdown("### Intent detected")
    detected = []
    if min_archive:
        detected.append("Archive opportunity")
    if wants_keywords:
        detected.append("Keyword generation")
    if wants_validate:
        detected.append("Trend validation")
    if not detected:
        detected.append("Story opportunity discovery")
    st.write(", ".join(detected))

    if wants_keywords and results:
        st.markdown("### Keyword pack from best match")
        pack = generate_keywords(results[0]["title"], "YouTube")
        st.json(pack)

    if wants_validate and results:
        st.markdown("### Validation summary")
        best = results[0]
        st.write(
            f"**{best['title']}** is currently classified as **{best['confidence_level']}** with "
            f"{best['source_count']} source(s), {best['item_count']} item(s), and opportunity score {best['opportunity_score']}."
        )
        if best["confidence_level"] in {"Watch", "Weak"}:
            st.warning("Treat this as a watch item, not a confirmed high-priority trend.")
        else:
            st.success("This has enough collected evidence for editorial consideration, subject to manual source verification.")

    st.markdown("### Matching editorial cards")
    for cl in results:
        render_cluster_card(cl)


def page_story_opportunities() -> None:
    st.title("Story Queue")
    render_editor_refresh_bar()
    c1, c2, c3 = st.columns(3)
    desk = c1.selectbox("Desk", ["All"] + DESKS)
    confidence = c2.selectbox("Confidence", ["All", "Verified", "Likely", "Watch", "Weak"])
    min_score = c3.slider("Minimum opportunity score", 0, 100, 0)
    clusters = load_clusters(desk=desk, confidence=confidence, min_score=min_score)
    st.caption(f"Showing {len(clusters)} source-backed opportunities.")
    for cl in clusters:
        render_cluster_card(cl)


def page_archive_matches() -> None:
    st.title("Archive")
    render_editor_refresh_bar()
    selected = st.session_state.get("selected_cluster_id")
    clusters = load_clusters()
    options = {f"{c['id']} · {c['title']}": c["id"] for c in clusters}
    if not options:
        st.info("No clusters yet.")
        return
    selected_label = None
    if selected:
        for label, cid in options.items():
            if cid == selected:
                selected_label = label
                break
    label = st.selectbox("Select topic", list(options.keys()), index=list(options.keys()).index(selected_label) if selected_label else 0)
    cluster_id = options[label]
    cl = cluster_detail(conn, cluster_id)
    render_cluster_card(cl, compact=True)

    st.subheader("Matched archive assets")
    if not cl["archive_matches"]:
        st.warning("No archive matches found. Upload archive CSV or rebuild matches after adding archive assets.")
    else:
        df = pd.DataFrame([{
            "Score": m["relevance_score"],
            "Title": m["title"],
            "Reason": m["match_reason"],
            "Recommended use": m["recommended_use"],
            "URL": m.get("url"),
        } for m in cl["archive_matches"]])
        st.dataframe(df, use_container_width=True, hide_index=True)

    with st.expander("Upload archive CSV"):
        st.write("Required useful columns: video_id, title, description, transcript, url, tags, published_at")
        file = st.file_uploader("Upload CSV", type=["csv"])
        if file and st.button("Import archive CSV"):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
                tmp.write(file.read())
                tmp_path = tmp.name
            inserted = import_archive_csv(conn, tmp_path)
            matches = rebuild_archive_matches(conn)
            st.success(f"Imported {inserted} archive assets and rebuilt {matches} matches")
            st.rerun()


def page_keyword_lab() -> None:
    st.title("Keyword Lab")
    render_editor_refresh_bar()
    default_topic = st.session_state.get("selected_topic", "")
    topic = st.text_input("Topic", value=default_topic, placeholder="Example: NEET counselling update")
    c1, c2 = st.columns(2)
    platform = c1.selectbox("Platform", PLATFORMS)
    desk = c2.selectbox("Desk context", DESKS)
    if not topic:
        st.info("Enter a topic or open this from a topic card.")
        return
    pack = generate_keywords(topic, platform)
    st.subheader("Recommended keyword pack")
    st.markdown("#### Primary")
    st.write(", ".join(pack["primary"]))
    st.markdown("#### Secondary / long-tail")
    st.write(", ".join(pack["secondary"]))
    st.markdown("#### Question keywords")
    st.write("\n".join([f"- {q}" for q in pack["questions"]]))
    st.markdown("#### Hashtags")
    st.write(" ".join(pack["hashtags"]))
    st.markdown("#### Avoid")
    st.warning("\n".join([f"- {x}" for x in pack["avoid"]]))


def page_brief_builder() -> None:
    st.title("Briefs")
    render_editor_refresh_bar()
    selected = st.session_state.get("selected_cluster_id")
    clusters = load_clusters()
    options = {f"{c['id']} · {c['title']}": c["id"] for c in clusters}
    if not options:
        st.info("No clusters yet.")
        return
    selected_label = None
    if selected:
        for label, cid in options.items():
            if cid == selected:
                selected_label = label
                break
    label = st.selectbox("Select topic", list(options.keys()), index=list(options.keys()).index(selected_label) if selected_label else 0)
    cluster_id = options[label]
    brief = generate_brief(conn, cluster_id)
    edited = st.text_area("Generated editorial brief", value=brief, height=650)
    cols = st.columns(3)
    if cols[0].button("Save as digest draft"):
        digest_id = save_digest(conn, f"Editorial Brief · {label}", edited, "email_draft")
        st.success(f"Saved digest draft #{digest_id}")
    cols[1].download_button("Download .md", edited, file_name="editorial_brief.md", mime="text/markdown")
    with cols[2]:
        st.caption("Copy from the text area for CMS/email use.")


def page_source_monitor() -> None:
    st.title("Source Monitor")
    srcs = rows(conn, "SELECT * FROM sources ORDER BY name")
    if srcs:
        st.dataframe(pd.DataFrame(srcs), use_container_width=True, hide_index=True)
    else:
        st.info("No sources configured yet.")
    st.subheader("Raw items")
    items = rows(conn, "SELECT source_name, source_tier, title, published_at, fetched_at, desk_hint, url FROM raw_items ORDER BY fetched_at DESC LIMIT 100")
    if items:
        st.dataframe(pd.DataFrame(items), use_container_width=True, hide_index=True)
    else:
        st.caption("No raw items yet.")


def page_admin() -> None:
    st.title("Admin")
    st.caption("Configure sources, ingest feeds, and rebuild the intelligence layer.")

    st.subheader("Ingest Google News RSS")
    c1, c2, c3 = st.columns(3)
    query = c1.text_input("Query", placeholder="leave blank for top headlines")
    country = c2.text_input("Country", value="IN")
    hours = c3.number_input("Window hours", min_value=1, max_value=72, value=6)
    source_name = st.text_input("Source name", value="Google News India")
    tier = st.selectbox("Credibility tier", ["official", "trusted", "standard", "unknown", "low"], index=2)
    url = google_news_rss_url(query or None, country=country, language="en", hours=int(hours))
    st.code(url)
    if st.button("Fetch RSS and rebuild"):
        try:
            items = fetch_rss(url, source_name=source_name, source_tier=tier)
            inserted = insert_raw_items(conn, items)
            upsert_source(conn, source_name, "rss", url, tier, True)
            clusters = rebuild_clusters(conn)
            matches = rebuild_archive_matches(conn)
            st.success(f"Fetched {len(items)} items, inserted {inserted}. Rebuilt {clusters} clusters and {matches} archive matches.")
            st.rerun()
        except Exception as exc:
            st.error(f"Fetch failed: {exc}")

    st.subheader("Manual source add/update")
    with st.form("source_form"):
        name = st.text_input("Name")
        s_type = st.selectbox("Type", ["rss", "api", "manual"])
        s_url = st.text_input("URL")
        s_tier = st.selectbox("Tier", ["official", "trusted", "standard", "unknown", "low"], index=2, key="manual_tier")
        active = st.checkbox("Active", value=True)
        submitted = st.form_submit_button("Save source")
        if submitted and name:
            upsert_source(conn, name, s_type, s_url, s_tier, active)
            st.success("Source saved")

    st.subheader("Maintenance")
    m1, m2, m3 = st.columns(3)
    if m1.button("Rebuild clusters"):
        clusters = rebuild_clusters(conn)
        st.success(f"Rebuilt {clusters} clusters")
    if m2.button("Rebuild archive matches"):
        matches = rebuild_archive_matches(conn)
        st.success(f"Rebuilt {matches} archive matches")
    if m3.button("Clear all data", type="secondary"):
        for table in ["cluster_items", "archive_matches", "topic_clusters", "raw_items", "archive_assets", "feedback", "digest_runs"]:
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
        st.warning("Cleared operational data")
        st.rerun()


def main() -> None:
    page = sidebar()
    if page == "Today’s Radar":
        page_radar()
    elif page == "Ask Radar":
        page_intent_search()
    elif page == "Story Queue":
        page_story_opportunities()
    elif page == "Archive":
        page_archive_matches()
    elif page == "Keyword Lab":
        page_keyword_lab()
    elif page == "Briefs":
        page_brief_builder()
    elif page == "Advanced":
        page_admin()
        st.divider()
        page_source_monitor()


if __name__ == "__main__":
    main()
