from __future__ import annotations

from datetime import datetime, timezone
from math import exp

from .config import SOURCE_TIERS


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def freshness_score(latest_published_at: str | None, now: datetime | None = None) -> float:
    dt = parse_dt(latest_published_at)
    if not dt:
        return 35.0
    now = now or datetime.now(timezone.utc)
    hours = max((now - dt).total_seconds() / 3600, 0)
    # Smooth decay: fresh under 1 hour ~90+, 6h ~45, 24h ~10.
    return round(100 * exp(-hours / 8), 2)


def source_score(source_tiers: list[str]) -> float:
    if not source_tiers:
        return 0.0
    vals = [SOURCE_TIERS.get(t, SOURCE_TIERS["unknown"]) for t in source_tiers]
    avg = sum(vals) / len(vals)
    diversity_bonus = min(len(set(source_tiers)) * 5, 15)
    return round(min(avg * 100 + diversity_bonus, 100), 2)


def momentum_score(item_count: int, source_count: int) -> float:
    # Conservative because we do not have true search volume yet.
    base = min(item_count * 12, 60)
    diversity = min(source_count * 10, 40)
    return round(min(base + diversity, 100), 2)


def confidence_label(item_count: int, source_count: int, source_score_value: float, freshness: float) -> str:
    if source_count >= 3 and item_count >= 4 and source_score_value >= 65 and freshness >= 35:
        return "Verified"
    if source_count >= 2 and item_count >= 2 and source_score_value >= 55:
        return "Likely"
    if item_count >= 1:
        return "Watch"
    return "Weak"


def opportunity_score(freshness: float, source_score_value: float, momentum: float, archive: float) -> float:
    return round((0.30 * freshness) + (0.25 * source_score_value) + (0.25 * momentum) + (0.20 * archive), 2)


def priority_from_score(score: float, confidence: str) -> str:
    if confidence in {"Weak", "Watch"} and score < 65:
        return "Watch"
    if score >= 75 and confidence in {"Verified", "Likely"}:
        return "High"
    if score >= 55:
        return "Medium"
    return "Watch"
