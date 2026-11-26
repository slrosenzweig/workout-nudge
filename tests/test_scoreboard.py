"""Monday closed-week scoreboard."""

from datetime import date
from pathlib import Path

from workout_nudge import sms
from workout_nudge.jobs import closed_week_scoreboard, report
from workout_nudge.store import Store

from conftest import A, B, make_cfg


def test_scoreboard_fragment_met_missed_none():
    assert "goal met" in sms.scoreboard_fragment(4, 3)
    assert "missed" in sms.scoreboard_fragment(2, 3)
    assert "no goal set" in sms.scoreboard_fragment(4, None)
    assert "1 day" in sms.scoreboard_fragment(1, None)


def test_closed_week_only_on_monday(tmp_path: Path):
    store = Store(tmp_path / "t.db")
    # Week of Mon Nov 16 – Sun Nov 22
    store.set_weekly_goal(A, "2026-11-16", 3)
    store.set_status("2026-11-16", A, True, source="oura")
    store.set_status("2026-11-18", A, True, source="oura")
    store.set_status("2026-11-20", A, True, source="oura")
    monday = date(2026, 11, 23)
    text = closed_week_scoreboard(store, A, monday)
    assert text is not None
    assert "3/3" in text
    assert "goal met" in text
    assert closed_week_scoreboard(store, A, date(2026, 11, 24)) is None  # Tuesday
    assert closed_week_scoreboard(store, A, date(2026, 11, 22)) is None  # Sunday


def test_report_includes_scoreboard_on_monday(tmp_path: Path, monkeypatch):
    cfg = make_cfg(tmp_path)
    store = Store(cfg.database_path)
    store.set_weekly_goal(A, "2026-11-16", 3)
    store.set_status("2026-11-16", A, True, source="oura")
    store.set_status("2026-11-18", A, True, source="oura")
    sent: list[tuple[str, str]] = []

    def fake_send(c, to, body):
        sent.append((to, body))
        return {"sid": "fake"}

    monkeypatch.setattr("workout_nudge.sms.send_sms", fake_send)
    bundle = {
        "day": "2026-11-23",
        "yesterday": "2026-11-22",
        "readiness": {"score": 80},
        "sleep": {"score": 80},
        "activity": {"score": 70},
        "yesterday_workouts": [],
    }
    result = report(
        cfg,
        store,
        today=date(2026, 11, 23),
        oura_bundle=bundle,
    )
    assert result.get("scoreboard")
    assert sent, "expected a report SMS"
    assert sent[0][0] == A
    assert "Last week you trained 2/3 days — missed" in sent[0][1]
    assert sent[0][1].startswith("Frank the Trainer:")
    assert sent[0][1].endswith("Reply STOP to opt out.")
