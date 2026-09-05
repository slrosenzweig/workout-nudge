"""Tests for weekly goal store helpers."""

from pathlib import Path

from workout_nudge.store import Store


def test_set_get_weekly_goal(tmp_path: Path):
    store = Store(tmp_path / "t.db")
    phone = "+15551110001"
    assert store.get_weekly_goal(phone, "2026-09-01") is None
    store.set_weekly_goal(phone, "2026-09-01", 4)
    assert store.get_weekly_goal(phone, "2026-09-01") == 4
    store.set_weekly_goal(phone, "2026-09-01", 6)
    assert store.get_weekly_goal(phone, "2026-09-01") == 6
    assert store.get_weekly_goal(phone, "2026-09-08") is None


def test_count_train_days(tmp_path: Path):
    store = Store(tmp_path / "t.db")
    phone = "+15551110002"
    # Mon–Sun week of 2026-08-31
    store.set_status("2026-08-31", phone, True, source="sms")   # Mon
    store.set_status("2026-09-01", phone, False, source="sms")  # Tue
    store.set_status("2026-09-02", phone, True, source="sms")   # Wed
    store.set_status("2026-09-03", phone, True, source="oura")  # Thu
    # Fri unknown, Sat unknown
    # Sun known rest
    store.set_status("2026-09-06", phone, False, source="sms")
    n = store.count_train_days(phone, "2026-08-31", "2026-09-06")
    assert n == 3  # Mon, Wed, Thu — Sunday not counted when not trained
