"""Scheduled jobs: morning nudge (~8:15) and 10:00 compare follow-up."""

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


def nudge(cfg: Config, store: Store | None = None) -> dict:
    """Morning job: Oura fetch, train/rest SMS, yesterday ask."""
    store = store or Store(cfg.database_path)
    a, b = cfg.require_participants()
    today = today_ny(cfg)
    yesterday = yesterday_ny(cfg)
    result: dict = {
        "day": today.isoformat(),
        "yesterday": yesterday.isoformat(),
        "decision": None,
        "actions": [],
    }

    # --- Oura for A ---
    if not cfg.oura_client_id or not cfg.oura_client_secret:
        raise RuntimeError("OURA_CLIENT_ID and OURA_CLIENT_SECRET required for nudge")

    client = oura_mod.OuraClient(
        client_id=cfg.oura_client_id,
        client_secret=cfg.oura_client_secret,
        tokens_path=cfg.oura_tokens_path,
    )
    bundle = client.fetch_day_bundle(today)
    readiness = bundle.get("readiness") or {}
    sleep = bundle.get("sleep")
    score = readiness.get("score")
    try:
        score_i = int(score) if score is not None else None
    except (TypeError, ValueError):
        score_i = None

    solid = rules.sleep_looks_solid(sleep if isinstance(sleep, dict) else None)
    train = rules.should_train(readiness_score=score_i, sleep_looks_solid=solid)
    result["decision"] = "train" if train else "rest"
    result["readiness_score"] = score_i

    if train and score_i is not None:
        body = sms.msg_train(score_i)
    else:
        body = sms.msg_rest()

    sms.send_sms(cfg, a, body)
    result["actions"].append({"to": "A", "kind": "train" if train else "rest"})

    # Train day: also SMS B if opted in. Rest day: A only.
    if train and store.is_opted_in(b):
        sms.send_sms(cfg, b, body)
        result["actions"].append({"to": "B", "kind": "train"})

    # --- Yesterday workouts ---
    y_workouts = bundle.get("yesterday_workouts") or []
    if rules.yesterday_trained(y_workouts):
        store.set_status(yesterday.isoformat(), a, True, source="oura")
        result["yesterday_trained_a"] = True
        result["actions"].append({"to": "A", "kind": "skip_ask_oura_yes"})
        # Still ask B if opted in and unknown
        status_b = store.get_status(yesterday.isoformat(), b)
        if store.is_opted_in(b) and (
            status_b is None or status_b.trained is None
        ):
            sms.send_sms(cfg, b, sms.msg_ask_yesterday())
            result["actions"].append({"to": "B", "kind": "ask_yesterday"})
    else:
        result["yesterday_trained_a"] = False
        # Ask A
        status_a = store.get_status(yesterday.isoformat(), a)
        if status_a is None or status_a.trained is None:
            sms.send_sms(cfg, a, sms.msg_ask_yesterday())
            result["actions"].append({"to": "A", "kind": "ask_yesterday"})
        if store.is_opted_in(b):
            status_b = store.get_status(yesterday.isoformat(), b)
            if status_b is None or status_b.trained is None:
                sms.send_sms(cfg, b, sms.msg_ask_yesterday())
                result["actions"].append({"to": "B", "kind": "ask_yesterday"})

    # If both already known after Oura auto-yes, send comparison
    if store.both_statuses_known(yesterday.isoformat(), a, b):
        if not store.comparison_was_sent(yesterday.isoformat()):
            _send_comparison(cfg, store, yesterday.isoformat(), a, b, result)

    log.info("nudge complete: %s", result)
    return result


def compare(cfg: Config, store: Store | None = None) -> dict:
    """10:00 follow-up: comparison, nag, or reminder."""
    store = store or Store(cfg.database_path)
    a, b = cfg.require_participants()
    yesterday = yesterday_ny(cfg)
    d = yesterday.isoformat()
    result: dict = {"yesterday": d, "actions": []}

    sa = store.get_status(d, a)
    sb = store.get_status(d, b)
    a_known = sa is not None and sa.trained is not None
    b_known = sb is not None and sb.trained is not None

    if a_known and b_known:
        if store.comparison_was_sent(d):
            result["actions"].append({"kind": "noop_already_sent"})
        else:
            _send_comparison(cfg, store, d, a, b, result)
        log.info("compare complete: %s", result)
        return result

    if a_known and not b_known:
        # SMS A that B hasn't answered. Don't invent. Don't text B if not opted in.
        sms.send_sms(cfg, a, sms.msg_partner_no_answer())
        result["actions"].append({"to": "A", "kind": "partner_no_answer"})
        # If B opted in, remind them once
        if store.is_opted_in(b):
            sms.send_sms(cfg, b, sms.msg_ask_yesterday())
            result["actions"].append({"to": "B", "kind": "reminder_ask"})
        log.info("compare complete: %s", result)
        return result

    if b_known and not a_known:
        if store.is_opted_in(b):
            sms.send_sms(cfg, b, sms.msg_partner_no_answer())
            result["actions"].append({"to": "B", "kind": "partner_no_answer"})
        sms.send_sms(cfg, a, sms.msg_ask_yesterday())
        result["actions"].append({"to": "A", "kind": "reminder_ask"})
        log.info("compare complete: %s", result)
        return result

    # Neither known: one reminder YES/NO (B only if opted in)
    sms.send_sms(cfg, a, sms.msg_ask_yesterday())
    result["actions"].append({"to": "A", "kind": "reminder_ask"})
    if store.is_opted_in(b):
        sms.send_sms(cfg, b, sms.msg_ask_yesterday())
        result["actions"].append({"to": "B", "kind": "reminder_ask"})

    log.info("compare complete: %s", result)
    return result


def _send_comparison(
    cfg: Config,
    store: Store,
    date: str,
    a: str,
    b: str,
    result: dict,
) -> None:
    sa = store.get_status(date, a)
    sb = store.get_status(date, b)
    assert sa and sb and sa.trained is not None and sb.trained is not None

    # A always gets partner (B) status
    sms.send_sms(cfg, a, sms.msg_partner_comparison(sb.trained))
    result["actions"].append({"to": "A", "kind": "comparison", "partner_trained": sb.trained})

    # B only if opted in
    if store.is_opted_in(b):
        sms.send_sms(cfg, b, sms.msg_partner_comparison(sa.trained))
        result["actions"].append(
            {"to": "B", "kind": "comparison", "partner_trained": sa.trained}
        )

    store.mark_comparison_sent(date)


def maybe_send_comparison_after_inbound(
    cfg: Config,
    store: Store,
    date: str,
) -> bool:
    """When both statuses known after inbound, SMS each whether the other trained."""
    a, b = cfg.require_participants()
    if not store.both_statuses_known(date, a, b):
        return False
    if store.comparison_was_sent(date):
        return False
    result: dict = {"actions": []}
    _send_comparison(cfg, store, date, a, b, result)
    return True
