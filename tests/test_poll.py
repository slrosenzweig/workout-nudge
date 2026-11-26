"""Reply-poll backup and inbound SID dedupe."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from workout_nudge.inbound import poll
from workout_nudge.store import Store

from conftest import A, B, make_cfg

ET = ZoneInfo("America/New_York")


def test_poll_confirms_new_message_and_dedupes(tmp_path: Path, monkeypatch):
    cfg = make_cfg(tmp_path)
    store = Store(cfg.database_path)
    store.set_opt_in(B, True)
    sent: list[tuple[str, str]] = []

    def fake_send(c, to, body):
        sent.append((to, body))
        return {"sid": "out"}

    monkeypatch.setattr("workout_nudge.sms.send_sms", fake_send)

    now = datetime(2026, 11, 26, 11, 27, tzinfo=ET)
    messages = [
        {"sid": "sid-train-1", "from": A, "body": "Train"},
    ]
    first = poll(cfg, store, now=now, messages=messages)
    assert first["processed"] == 1
    assert first["confirmed"] == 1
    assert store.get_status("2026-11-26", A).today_intent == "train"
    assert store.inbound_was_processed("sid-train-1")
    assert store.inbound_confirm_sent("sid-train-1")
    assert len(sent) == 1
    assert sent[0][0] == A
    assert "Got it" in sent[0][1]

    # Second poll must not re-send
    sent.clear()
    second = poll(cfg, store, now=now, messages=messages)
    assert second["processed"] == 0
    assert second["skipped"] == 1
    assert sent == []


def test_poll_skips_confirm_when_webhook_already_confirmed(
    tmp_path: Path, monkeypatch
):
    cfg = make_cfg(tmp_path)
    store = Store(cfg.database_path)
    sid = "sid-train-2"
    # Webhook already applied Train and sent TwiML confirm
    store.set_today_intent("2026-11-26", A, "train")
    store.mark_inbound_processed(sid, confirm_sent=True)

    sent: list = []
    monkeypatch.setattr(
        "workout_nudge.sms.send_sms",
        lambda c, to, body: sent.append((to, body)) or {"sid": "out"},
    )
    now = datetime(2026, 11, 26, 11, 57, tzinfo=ET)
    result = poll(
        cfg,
        store,
        now=now,
        messages=[{"sid": sid, "from": A, "body": "Train"}],
    )
    assert result["skipped"] == 1
    assert result["confirmed"] == 0
    assert sent == []


def test_poll_ignores_unknown_sender(tmp_path: Path, monkeypatch):
    cfg = make_cfg(tmp_path)
    store = Store(cfg.database_path)
    sent: list = []
    monkeypatch.setattr(
        "workout_nudge.sms.send_sms",
        lambda c, to, body: sent.append((to, body)) or {"sid": "out"},
    )
    now = datetime(2026, 11, 26, 12, 0, tzinfo=ET)
    result = poll(
        cfg,
        store,
        now=now,
        messages=[
            {
                "sid": "sid-unknown-1",
                "from": "+15559999999",
                "body": "Train",
            }
        ],
    )
    assert result["skipped"] == 1
    assert result["processed"] == 0
    assert sent == []
    assert store.get_status("2026-11-26", A) is None
