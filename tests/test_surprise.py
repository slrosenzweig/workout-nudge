"""Surprise-text hooks, caps, quiet hours, and rolls."""

from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from workout_nudge.store import Store
from workout_nudge.surprise import (
    can_send,
    days_left_in_week,
    in_quiet_hours,
    pick_hook_a,
    pick_hook_b,
    surprise,
)

from conftest import A, B, make_cfg

ET = ZoneInfo("America/New_York")


def test_hooks_priority():
    today = date(2026, 11, 26)  # Thursday
    assert pick_hook_a(trained=3, goal=3, streak=0, days_left=4, today=today) == "hit_goal"
    assert pick_hook_a(trained=2, goal=3, streak=0, days_left=4, today=today) == "one_away"
    assert pick_hook_a(trained=2, goal=5, streak=3, days_left=4, today=today) == "streak"
    # 1 of 3 with 2 days left: needed=2 >= 2-1 → behind
    assert (
        pick_hook_a(trained=1, goal=3, streak=0, days_left=2, today=date(2026, 11, 28))
        == "falling_behind"
    )
    # 0 midweek (Thursday) also behind
    assert pick_hook_a(trained=0, goal=3, streak=0, days_left=4, today=today) == "falling_behind"
    # Monday with plenty of days and a start: no hook
    assert (
        pick_hook_a(trained=1, goal=3, streak=0, days_left=6, today=date(2026, 11, 23))
        is None
    )


def test_days_left_and_quiet_hours():
    assert days_left_in_week(date(2026, 11, 26), trained_today=False) == 4  # Thu–Sun
    assert days_left_in_week(date(2026, 11, 26), trained_today=True) == 3
    assert days_left_in_week(date(2026, 11, 29), trained_today=False) == 1  # Sunday
    assert in_quiet_hours(datetime(2026, 11, 26, 8, 59, tzinfo=ET))
    assert in_quiet_hours(datetime(2026, 11, 26, 21, 0, tzinfo=ET))
    assert not in_quiet_hours(datetime(2026, 11, 26, 12, 0, tzinfo=ET))
    assert not in_quiet_hours(datetime(2026, 11, 26, 17, 0, tzinfo=ET))


def test_caps_and_no_back_to_back():
    today = date(2026, 11, 26)
    assert can_send(
        dates_this_week=["2026-11-23", "2026-11-25"],
        last_date="2026-11-25",
        today=today,
        cap=3,
        no_back_to_back=True,
    ) is False  # yesterday
    assert can_send(
        dates_this_week=["2026-11-23", "2026-11-24", "2026-11-26"],
        last_date="2026-11-26",
        today=today,
        cap=3,
        no_back_to_back=True,
    ) is False  # already today
    assert can_send(
        dates_this_week=["2026-11-23", "2026-11-25", "2026-11-27"],
        last_date="2026-11-27",
        today=date(2026, 11, 29),
        cap=3,
        no_back_to_back=True,
    ) is False  # cap
    assert can_send(
        dates_this_week=["2026-11-23"],
        last_date="2026-11-23",
        today=today,
        cap=3,
        no_back_to_back=True,
    ) is True


def test_surprise_one_away_and_b_quiet(tmp_path: Path, monkeypatch):
    cfg = make_cfg(tmp_path)
    store = Store(cfg.database_path)
    store.set_opt_in(B, True)
    store.set_weekly_goal(A, "2026-11-23", 3)
    store.set_status("2026-11-23", A, True, source="oura")
    store.set_status("2026-11-25", A, True, source="oura")  # 2 of 3 → one_away
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "workout_nudge.sms.send_sms",
        lambda c, to, body: sent.append((to, body)) or {"sid": "out"},
    )
    now = datetime(2026, 11, 26, 17, 0, tzinfo=ET)
    result = surprise(cfg, store, now=now, roll_a=0.0, roll_b=0.0)
    hooks = {a["to"]: a["hook"] for a in result["actions"] if a.get("kind") == "surprise"}
    assert hooks["A"] == "one_away"
    assert hooks["B"] == "quiet"
    bodies = {to: body for to, body in sent}
    assert "one workout away" in bodies[A]
    assert bodies[A].startswith("Frank the Trainer:")
    assert "Reply STOP to opt out." in bodies[A]
    assert "nudge" in bodies[B].lower()
    assert A[-4:] not in bodies[B]  # no A number in B text
    # second send same day blocked
    sent.clear()
    again = surprise(cfg, store, now=now, roll_a=0.0, roll_b=0.0)
    assert all(a.get("kind") != "surprise" for a in again["actions"])
    assert sent == []


def test_surprise_quiet_hours_and_failed_roll(tmp_path: Path, monkeypatch):
    cfg = make_cfg(tmp_path)
    store = Store(cfg.database_path)
    store.set_weekly_goal(A, "2026-11-23", 3)
    store.set_status("2026-11-23", A, True, source="oura")
    store.set_status("2026-11-24", A, True, source="oura")
    store.set_status("2026-11-25", A, True, source="oura")  # hit goal
    sent: list = []
    monkeypatch.setattr(
        "workout_nudge.sms.send_sms",
        lambda c, to, body: sent.append((to, body)) or {"sid": "out"},
    )
    night = datetime(2026, 11, 26, 21, 30, tzinfo=ET)
    result = surprise(cfg, store, now=night, roll_a=0.0, roll_b=1.0)
    assert result["actions"] == [{"kind": "quiet_hours"}]
    assert sent == []

    noon = datetime(2026, 11, 26, 12, 0, tzinfo=ET)
    result = surprise(cfg, store, now=noon, roll_a=0.99, roll_b=1.0)  # fail rolls
    assert any(a.get("kind") == "skipped" and a.get("to") == "A" for a in result["actions"])
    assert sent == []
