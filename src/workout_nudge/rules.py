"""Workout qualification and train/rest decision rules (LOCKED)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping


def duration_minutes(w: Mapping[str, Any]) -> int:
    start = datetime.fromisoformat(w["start_datetime"])
    end = datetime.fromisoformat(w["end_datetime"])
    return max(0, int((end - start).total_seconds() // 60))


def qualifies_workout(w: Mapping[str, Any]) -> bool:
    """Return True if workout counts toward yesterday-trained.

    Locked product rules — do not change without explicit product approval.
    """
    mins = duration_minutes(w)
    source = (w.get("source") or "").lower()
    intensity = (w.get("intensity") or "").lower()
    activity = (w.get("activity") or "").lower()
    if activity in {"walking", "housework", "indoor_cycling"} and source != "manual":
        return False
    if source == "manual":
        return True
    if intensity in {"moderate", "high", "medium"} and mins >= 20:
        return True
    if mins >= 20 and activity not in {"walking"}:
        return True
    return False


def should_train(*, readiness_score: int | None, sleep_looks_solid: bool) -> bool:
    """Train if readiness ~70+ and sleep looks solid; else rest."""
    if readiness_score is None:
        return False
    return readiness_score >= 70 and sleep_looks_solid


def sleep_looks_solid(sleep: Mapping[str, Any] | None) -> bool:
    """Heuristic: solid if score >= 70 or efficiency/total sleep reasonable."""
    if not sleep:
        return False
    # Oura daily_sleep: contributors / score fields vary by API version
    score = sleep.get("score")
    if score is not None:
        try:
            return int(score) >= 70
        except (TypeError, ValueError):
            pass
    contributors = sleep.get("contributors") or {}
    total = contributors.get("total_sleep")
    if total is not None:
        try:
            return int(total) >= 70
        except (TypeError, ValueError):
            pass
    # Fallback: deep + rem minutes if present on nested sleep
    return False


def yesterday_trained(workouts: list[Mapping[str, Any]]) -> bool:
    return any(qualifies_workout(w) for w in workouts)
