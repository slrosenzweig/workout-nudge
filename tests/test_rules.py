"""Tests for locked qualifies_workout rules."""

from workout_nudge.rules import duration_minutes, qualifies_workout


def _w(**kwargs):
    base = {
        "start_datetime": "2026-01-01T10:00:00-05:00",
        "end_datetime": "2026-01-01T10:30:00-05:00",
        "source": "automatic",
        "intensity": "moderate",
        "activity": "strength",
    }
    base.update(kwargs)
    return base


def test_manual_source_always_qualifies_even_5_min_walking():
    w = _w(
        source="manual",
        activity="walking",
        intensity="easy",
        start_datetime="2026-01-01T10:00:00-05:00",
        end_datetime="2026-01-01T10:05:00-05:00",
    )
    assert duration_minutes(w) == 5
    assert qualifies_workout(w) is True


def test_auto_walking_30_min_does_not_qualify():
    w = _w(
        source="automatic",
        activity="walking",
        intensity="moderate",
        start_datetime="2026-01-01T10:00:00-05:00",
        end_datetime="2026-01-01T10:30:00-05:00",
    )
    assert duration_minutes(w) == 30
    assert qualifies_workout(w) is False


def test_auto_barre_strength_52_min_moderate_does_qualify():
    w = _w(
        source="automatic",
        activity="barre",
        intensity="moderate",
        start_datetime="2026-01-01T10:00:00-05:00",
        end_datetime="2026-01-01T10:52:00-05:00",
    )
    assert duration_minutes(w) == 52
    assert qualifies_workout(w) is True

    w2 = _w(
        source="automatic",
        activity="strength",
        intensity="moderate",
        start_datetime="2026-01-01T10:00:00-05:00",
        end_datetime="2026-01-01T10:52:00-05:00",
    )
    assert qualifies_workout(w2) is True


def test_auto_walking_10_min_does_not_qualify():
    w = _w(
        source="automatic",
        activity="walking",
        intensity="low",
        start_datetime="2026-01-01T10:00:00-05:00",
        end_datetime="2026-01-01T10:10:00-05:00",
    )
    assert duration_minutes(w) == 10
    assert qualifies_workout(w) is False
