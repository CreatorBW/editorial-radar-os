from __future__ import annotations

APP_NAME = "Editorial Radar OS"
DEFAULT_DB_PATH = "editorial_radar.db"
DEFAULT_COUNTRY = "IN"
DEFAULT_LANGUAGE = "en"
DEFAULT_TIME_WINDOW_HOURS = 6

DESKS = [
    "National",
    "Politics",
    "World",
    "Business",
    "Sports",
    "Entertainment",
    "Technology",
    "Health",
    "Education",
    "Crime",
    "Lifestyle",
    "Archive",
]

SOURCE_TIERS = {
    "official": 1.00,
    "trusted": 0.85,
    "standard": 0.65,
    "unknown": 0.45,
    "low": 0.25,
}

PLATFORMS = ["Google Search", "YouTube", "Shorts", "Facebook", "Instagram", "Discover", "Website SEO"]

EDITORIAL_RULES = [
    "Never call an item trending unless evidence is shown.",
    "Separate facts, signals, interpretation, and recommendation.",
    "Show source count, freshness, confidence, and limitations.",
    "Never fabricate search volume, source claims, or archive matches.",
    "Flag weak or single-source signals as Watch, not High Priority.",
]
