"""Shared inbound SMS handling for the webhook and the reply-poll backup."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from workout_nudge import jobs, sms
from workout_nudge.parse import Intent, parse_message
from workout_nudge.store import Store

if TYPE_CHECKING:
    from workout_nudge.config import Config

log = logging.getLogger(__name__)


def apply_inbound(
    cfg: Config,
    store: Store,
    *,
    from_num: str,
    body: str,
    now: datetime | None = None,
) -> str:
    """Apply one inbound message and return a confirm/reply body (maybe empty).

    Partner-update and weekly partner-commit SMS are sent directly when needed.
    """
    a = cfg.participant_a_number or ""
    b = cfg.participant_b_number or ""
    known = {a, b} - {""}
    if from_num not in known:
        log.info("Ignoring SMS from unknown number")
        return ""

    parsed = parse_message(body)
    intent = parsed.intent
    tz = ZoneInfo(cfg.tz)
    now = now or datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    else:
        now = now.astimezone(tz)
    today_d = now.date()
    today = today_d.isoformat()
    yesterday = (today_d - timedelta(days=1)).isoformat()

    if intent is Intent.OPT_OUT:
        store.set_opt_in(from_num, False)
        return sms.msg_opt_out_confirm()

    if intent is Intent.OPT_IN:
        store.set_opt_in(from_num, True)
        return sms.msg_opt_in_confirm()

    if intent is Intent.WORKOUT_YES:
        if from_num == b:
            store.set_opt_in(from_num, True)
        store.set_status(yesterday, from_num, True, source="sms")
        if jobs.maybe_send_partner_update_after_inbound(cfg, store, now=now):
            return ""
        return sms.msg_got_it()

    if intent is Intent.WORKOUT_NO:
        if from_num == b:
            store.set_opt_in(from_num, True)
        store.set_status(yesterday, from_num, False, source="sms")
        if jobs.maybe_send_partner_update_after_inbound(cfg, store, now=now):
            return ""
        return sms.msg_got_it()

    if intent is Intent.TODAY_TRAIN:
        if from_num == b:
            store.set_opt_in(from_num, True)
        store.set_today_intent(today, from_num, "train")
        if jobs.maybe_send_partner_update_after_inbound(cfg, store, now=now):
            return ""
        return sms.msg_got_it()

    if intent is Intent.TODAY_REST:
        if from_num == b:
            store.set_opt_in(from_num, True)
        store.set_today_intent(today, from_num, "rest")
        if jobs.maybe_send_partner_update_after_inbound(cfg, store, now=now):
            return ""
        return sms.msg_got_it()

    if intent is Intent.WEEKLY_COMMIT:
        days = parsed.days
        if days is None or days < 0 or days > 7:
            return ""
        if from_num == b:
            store.set_opt_in(from_num, True)
        week_of = jobs.commitment_week_of(today_d).isoformat()
        store.set_weekly_goal(from_num, week_of, days)
        reply = sms.msg_weekly_locked(days)
        goal_a = store.get_weekly_goal(a, week_of) if a else None
        goal_b = store.get_weekly_goal(b, week_of) if b else None
        if goal_a is not None and goal_b is not None:
            sms.send_sms(cfg, a, sms.msg_weekly_partner_commit(goal_a, goal_b))
            if store.is_opted_in(b) or from_num == b:
                sms.send_sms(cfg, b, sms.msg_weekly_partner_commit(goal_b, goal_a))
        return reply

    return ""


def poll(
    cfg: Config,
    store: Store | None = None,
    *,
    now: datetime | None = None,
    messages: list[dict[str, Any]] | None = None,
) -> dict:
    """Backup inbound poll: list Twilio messages since last_poll_at and apply them.

    Dedupes with ``processed_inbound`` SIDs. Sends a confirm SMS only when the
    webhook has not already confirmed that message.
    """
    store = store or Store(cfg.database_path)
    tz = ZoneInfo(cfg.tz)
    now = now or datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    else:
        now = now.astimezone(tz)

    result: dict = {"actions": [], "processed": 0, "skipped": 0, "confirmed": 0}
    last_raw = store.get_meta("last_poll_at")
    if last_raw:
        try:
            sent_after = datetime.fromisoformat(last_raw)
            if sent_after.tzinfo is None:
                sent_after = sent_after.replace(tzinfo=tz)
        except ValueError:
            sent_after = now - timedelta(hours=36)
    else:
        sent_after = now - timedelta(hours=36)

    if messages is None:
        messages = sms.list_inbound_messages(cfg, sent_after=sent_after)

    a, b = cfg.require_participants()
    known = {a, b}

    for msg in messages:
        sid = str(msg.get("sid") or msg.get("Sid") or "")
        from_num = str(msg.get("from") or msg.get("From") or "")
        body = str(msg.get("body") or msg.get("Body") or "")
        if from_num not in known:
            result["skipped"] += 1
            continue
        if sid and store.inbound_was_processed(sid):
            result["skipped"] += 1
            result["actions"].append({"sid": sid, "kind": "already_processed"})
            continue

        already_confirmed = bool(sid and store.inbound_confirm_sent(sid))
        reply = apply_inbound(cfg, store, from_num=from_num, body=body, now=now)
        confirm_sent = False
        if reply and not already_confirmed:
            sms.send_sms(cfg, from_num, reply)
            confirm_sent = True
            result["confirmed"] += 1
            result["actions"].append({"sid": sid, "kind": "confirm", "to": from_num})
        elif reply and already_confirmed:
            result["actions"].append({"sid": sid, "kind": "confirm_already_sent"})
        else:
            result["actions"].append({"sid": sid, "kind": "applied_no_confirm"})

        if sid:
            store.mark_inbound_processed(sid, confirm_sent=confirm_sent or already_confirmed)
        result["processed"] += 1

    store.set_meta("last_poll_at", now.isoformat())
    result["last_poll_at"] = now.isoformat()
    log.info("poll complete: %s", result)
    return result
