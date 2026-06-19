# Editorial Radar OS

A professional, intent-based editorial intelligence web app for trending news, source-backed story opportunities, keyword generation, and archive-video matching.

This build is optimized for editorial users, not tech users:

- Editors land on **Today’s Radar**.
- Every editor-facing page has **Refresh Radar**.
- Admin/source mechanics are hidden inside **Advanced**.
- Demo loading is one click.
- Evidence is still available behind "Why am I seeing this?"

## Setup

```bash
cd editorial_radar_os
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Editorial workflow

1. Open the app.
2. Click **Refresh Radar**.
3. Review **Best Now**, **Archive Ready**, or **Needs Watch**.
4. Open evidence when needed.
5. Generate brief, keywords, or archive matches from the same card.

## Fast demo

In the sidebar or top bar, click:

```text
Load Demo
```

This creates demo sources, news items, topic clusters, and archive matches.

## Live refresh

Click:

```text
Refresh Radar
```

The app fetches a default set of India editorial signals, rebuilds clusters, and refreshes archive matches.

Default refresh queries:

```text
India top headlines
India politics
NEET counselling
Delhi rain
Iran Israel
Sensex Nifty
India cricket squad
Bollywood OTT
```

## Advanced source controls

For source configuration and manual RSS ingestion, go to:

```text
Advanced
```

Editors should not need this page for daily use.

## Archive import

Go to:

```text
Archive → Upload archive CSV
```

Supported columns:

```text
video_id,title,description,transcript,url,tags,published_at,performance_note
```

Sample file:

```text
assets/sample_archive.csv
```

## Run tests

```bash
python -m unittest discover -s tests -v
python -m compileall app.py radar tests
```

Expected: all tests pass and all Python files compile.

## Current limitations

- Momentum is a source/item-count proxy, not exact search volume.
- Google News RSS is treated as a feed source, not a guaranteed official trends API.
- No AI API is required yet; brief/keyword generation is deterministic for testability.
- Email/WhatsApp delivery is not enabled yet.

## Next build

Recommended next steps:

1. Add background scheduled refresh.
2. Add SendGrid email digest.
3. Add OpenAI/Azure OpenAI source-grounded brief enhancement.
4. Add real archive database connector.
5. Add editor login and desk personalization.
6. Add watchlists and alert rules.

## Hotfix: clustering contamination

If a topic card shows unrelated keywords, rebuild with this version. The clustering logic now:

- removes Google News source suffixes from headlines,
- ignores common source/publication names as keywords,
- prevents loose cluster drift,
- requires stronger token/entity overlap before merging articles.

After deploying, click **Advanced → Clear all data**, then **Refresh Radar**.
