"""Scheduled jobs: sync (8:00), report (8:30), compare (10:00), weekly (Sun 11:00)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from workout_nudge import oura as oura_mod
from workout_nudge import rules, sms
from workout_nudge.store import Store

if TYPE_CHECKING:
    from workout_nudge.config import Config

log = logging.getLogger(__name__)


def _tz(cfg: Config) -> ZoneInfo:
    return ZoneInfo(cfg.tz)


def today_ny(cfg: Config) -> date:
    return datetime.now(_tz(cfg)).date()


def yesterday_ny(cfg: Config) -> date:
    return today_ny(cfg) - timedelta(days=1)


def monday_of(d: date) -> date:
    """Monday of the calendar week containing d (Mon–Sun weeks)."""
    return d - timedelta(days=d.weekday())


def next_monday(d: date) -> date:
    """Next Monday strictly after d (if d is Monday, returns +7)."""
    return d + timedelta(days=(7 - d.weekday()))


def commitment_week_of(d: date) -> date:
    """week_of for a weekly commitment reply.

    Sunday (after weekly ask): next Monday. Otherwise: Monday of the current week
    (the week most recently asked about on the prior Sunday).
    """
    if d.weekday() == 6:  # Sunday
        return d + timedelta(days=1)
    return monday_of(d)


def _score(obj: dict | None, key: str = "score") -> int | None:
    if not obj:
        return None
    val = obj.get(key)
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def sync(cfg: Config, store: Store | None = None) -> dict:
    """8:00 job: remind A to open Oura and sync the ring (no scores)."""
    store = store or Store(cfg.database_path)
    a, _b = cfg.require_participants()
    today = today_ny(cfg)
    result: dict = {"day": today.isoformat(), "actions": []}
    sms.send_sms(cfg, a, sms.msg_sync_ring())
    result["actions"].append({"to": "A", "kind": "sync_ring"})
    log.info("sync complete: %s", result)
    return result


def report(cfg: Config, store: Store | None = None) -> dict:
    """8:30 job: Oura fetch, today intent, yesterday status, SMS report (no partner)."""
    store = store or Store(cfg.database_path)
    a, b = cfg.require_participants()
    today = today_ny(cfg)
    yesterday = yesterday_ny(cfg)
    today_s = today.isoformat()
    yesterday_s = yesterday.isoformat()
    result: dict = {
        "day": today_s,
        "yesterday": yesterday_s,
        "decision": None,
        "actions": [],
    }

    if not cfg.oura_client_id or not cfg.oura_client_secret:
        raise RuntimeError(
            "OURA_CLIENT_ID and OURA_CLIENT_SECRET required for report"
        )

    client = oura_mod.OuraClient(
        client_id=cfg.oura_client_id,
        client_secret=cfg.oura_client_secret,
        tokens_path=cfg.oura_tokens_path,
    )
    bundle = client.fetch_day_bundle(today)
    readiness = bundle.get("readiness") if isinstance(bundle.get("readiness"), dict) else None
    sleep = bundle.get("sleep") if isinstance(bundle.get("sleep"), dict) else None
    activity = bundle.get("activity") if isinstance(bundle.get("activity"), dict) else None

    score_i = _score(readiness)
    activity_i = _score(activity)
    solid = rules.sleep_looks_solid(sleep)
    train = rules.should_train(readiness_score=score_i, sleep_looks_solid=solid)
    today_intent = "train" if train else "rest"
    result["decision"] = today_intent
    result["readiness_score"] = score_i
    result["activity_score"] = activity_i

    store.set_today_intent(today_s, a, today_intent)

    # Yesterday for A: Oura lock or ask
    y_workouts = bundle.get("yesterday_workouts") or []
    ask_yesterday_a = False
    yesterday_trained_a: bool | None = None
    if rules.yesterday_trained(y_workouts):
        store.set_status(yesterday_s, a, True, source="oura")
        yesterday_trained_a = True
        result["yesterday_trained_a"] = True
        result["actions"].append({"to": "A", "kind": "skip_ask_oura_yes"})
    else:
        result["yesterday_trained_a"] = False
        status_a = store.get_status(yesterday_s, a)
        if status_a is None or status_a.trained is None:
            ask_yesterday_a = True
        else:
            yesterday_trained_a = status_a.trained

    sms.send_sms(
        cfg,
        a,
        sms.msg_report_a(
            readiness_score=score_i,
            activity_score=activity_i,
            today_intent=today_intent,
            yesterday_trained=yesterday_trained_a,
            ask_yesterday=ask_yesterday_a,
        ),
    )
    result["actions"].append({"to": "A", "kind": "report"})

    # B: ask YES/NO + TRAIN/REST if opted in (no partner comparison)
    if store.is_opted_in(b):
        need_y = not store.yesterday_known(yesterday_s, b)
        need_i = not store.today_intent_known(today_s, b)
        if need_y or need_i:
            if need_y and need_i:
                body = sms.msg_ask_b()
            else:
                body = sms.msg_ask_incomplete(
                    need_yesterday=need_y, need_intent=need_i
                )
            sms.send_sms(cfg, b, body)
            result["actions"].append({"to": "B", "kind": "ask_yesterday_and_intent"})

    log.info("report complete: %s", result)
    return result


# Deprecated alias for the old morning job
def nudge(cfg: Config, store: Store | None = None) -> dict:
    """Alias for report (deprecated name)."""
    return report(cfg, store)


def compare(cfg: Config, store: Store | None = None) -> dict:
    """10:00 follow-up: partner updates (yesterday + today_intent), or reminders."""
    store = store or Store(cfg.database_path)
    a, b = cfg.require_participants()
    today = today_ny(cfg)
    yesterday = yesterday_ny(cfg)
    today_s = today.isoformat()
    yesterday_s = yesterday.isoformat()
    result: dict = {
        "day": today_s,
        "yesterday": yesterday_s,
        "actions": [],
    }

    if store.partner_update_was_sent(today_s):
        result["actions"].append({"kind": "noop_already_sent"})
        log.info("compare complete: %s", result)
        return result

    if store.both_complete(yesterday_s, today_s, a, b):
        _send_partner_updates(cfg, store, yesterday_s, today_s, a, b, result)
        log.info("compare complete: %s", result)
        return result

    a_done = store.participant_complete(yesterday_s, today_s, a)
    b_done = store.participant_complete(yesterday_s, today_s, b)

    if a_done and not b_done:
        sms.send_sms(cfg, a, sms.msg_partner_no_update())
        result["actions"].append({"to": "A", "kind": "partner_no_update"})
        if store.is_opted_in(b):
            _remind_incomplete(cfg, store, yesterday_s, today_s, b, "B", result)
        log.info("compare complete: %s", result)
        return result

    if b_done and not a_done:
        if store.is_opted_in(b):
            sms.send_sms(cfg, b, sms.msg_partner_no_update())
            result["actions"].append({"to": "B", "kind": "partner_no_update"})
        _remind_incomplete(cfg, store, yesterday_s, today_s, a, "A", result)
        log.info("compare complete: %s", result)
        return result

    # Neither complete
    _remind_incomplete(cfg, store, yesterday_s, today_s, a, "A", result)
    if store.is_opted_in(b):
        _remind_incomplete(cfg, store, yesterday_s, today_s, b, "B", result)

    log.info("compare complete: %s", result)
    return result


def _remind_incomplete(
    cfg: Config,
    store: Store,
    yesterday_s: str,
    today_s: str,
    phone: str,
    label: str,
    result: dict,
) -> None:
    need_y = not store.yesterday_known(yesterday_s, phone)
    need_i = not store.today_intent_known(today_s, phone)
    if not need_y and not need_i:
        return
    sms.send_sms(
        cfg,
        phone,
        sms.msg_ask_incomplete(need_yesterday=need_y, need_intent=need_i),
    )
    result["actions"].append(
        {
            "to": label,
            "kind": "reminder_ask",
            "need_yesterday": need_y,
            "need_intent": need_i,
        }
    )


def _send_partner_updates(
    cfg: Config,
    store: Store,
    yesterday_s: str,
    today_s: str,
    a: str,
    b: str,
    result: dict,
) -> None:
    sa_y = store.get_status(yesterday_s, a)
    sb_y = store.get_status(yesterday_s, b)
    sa_t = store.get_status(today_s, a)
    sb_t = store.get_status(today_s, b)
    assert (
        sa_y
        and sb_y
        and sa_t
        and sb_t
        and sa_y.trained is not None
        and sb_y.trained is not None
        and sa_t.today_intent in ("train", "rest")
        and sb_t.today_intent in ("train", "rest")
    )

    # A always gets partner (B) status
    sms.send_sms(
        cfg,
        a,
        sms.msg_partner_update(
            partner_trained_yesterday=sb_y.trained,
            partner_today_intent=sb_t.today_intent,
        ),
    )
    result["actions"].append(
        {
            "to": "A",
            "kind": "partner_update",
            "partner_trained": sb_y.trained,
            "partner_intent": sb_t.today_intent,
        }
    )

    if store.is_opted_in(b):
        sms.send_sms(
            cfg,
            b,
            sms.msg_partner_update(
                partner_trained_yesterday=sa_y.trained,
                partner_today_intent=sa_t.today_intent,
            ),
        )
        result["actions"].append(
            {
                "to": "B",
                "kind": "partner_update",
                "partner_trained": sa_y.trained,
                "partner_intent": sa_t.today_intent,
            }
        )

    store.mark_partner_update_sent(today_s)


def weekly(cfg: Config, store: Store | None = None) -> dict:
    """Sunday ~11:00: recap current Mon–Sun week, ask for next week's commitment."""
    store = store or Store(cfg.database_path)
    a, b = cfg.require_participants()
    today = today_ny(cfg)
    week_start = monday_of(today)
    week_end = week_start + timedelta(days=6)  # Sunday
    week_of = week_start.isoformat()
    upcoming = next_monday(today)
    upcoming_s = upcoming.isoformat()

    result: dict = {
        "day": today.isoformat(),
        "week_of": week_of,
        "week_end": week_end.isoformat(),
        "upcoming_week_of": upcoming_s,
        "actions": [],
    }

    # Recipients: A always; B only if opted in
    recipients: list[tuple[str, str]] = [("A", a)]
    if store.is_opted_in(b):
        recipients.append(("B", b))

    # Load goals + actuals
    stats: dict[str, dict] = {}
    for label, phone in [("A", a), ("B", b)]:
        goal = store.get_weekly_goal(phone, week_of)
        days = store.count_train_days(phone, week_of, week_end.isoformat())
        stats[label] = {"phone": phone, "goal": goal, "days": days}

    b_opted = store.is_opted_in(b)

    for label, phone in recipients:
        mine = stats[label]
        partner_label = "B" if label == "A" else "A"
        partner = stats[partner_label]
        include_partner = (label == "A" and b_opted) or (label == "B")
        # Partner known if they have a goal or any counted train days / we always
        # have a day count (may be 0). For A→B: include if B opted in.
        # For B→A: always include A's stats.
        body = sms.msg_weekly_recap(
            my_days=mine["days"],
            my_goal=mine["goal"],
            partner_days=partner["days"] if include_partner else None,
            partner_goal=partner["goal"] if include_partner else None,
            include_partner=include_partner,
        )
        sms.send_sms(cfg, phone, body)
        result["actions"].append(
            {
                "to": label,
                "kind": "weekly_recap",
                "days": mine["days"],
                "goal": mine["goal"],
            }
        )

    for label, phone in recipients:
        sms.send_sms(cfg, phone, sms.msg_weekly_ask())
        result["actions"].append({"to": label, "kind": "weekly_ask", "week_of": upcoming_s})

    log.info("weekly complete: %s", result)
    return result


def maybe_send_partner_update_after_inbound(
    cfg: Config,
    store: Store,
) -> bool:
    """Late path: if both complete, local time ≥10:00 NY, and not yet sent."""
    a, b = cfg.require_participants()
    tz = _tz(cfg)
    now = datetime.now(tz)
    if now.hour < 10:
        return False
    today_s = now.date().isoformat()
    yesterday_s = (now.date() - timedelta(days=1)).isoformat()
    if store.partner_update_was_sent(today_s):
        return False
    if not store.both_complete(yesterday_s, today_s, a, b):
        return False
    result: dict = {"actions": []}
    _send_partner_updates(cfg, store, yesterday_s, today_s, a, b, result)
    return True


# Backward-compatible name
def maybe_send_comparison_after_inbound(
    cfg: Config,
    store: Store,
    date: str | None = None,
) -> bool:
    return maybe_send_partner_update_after_inbound(cfg, store)
