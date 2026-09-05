"""Twilio inbound SMS webhook (Flask)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from flask import Flask, Request, Response, request

from workout_nudge import jobs, sms
from workout_nudge.parse import Intent, parse_message
from workout_nudge.store import Store

if TYPE_CHECKING:
    from workout_nudge.config import Config

log = logging.getLogger(__name__)


def create_app(cfg: Config, store: Store | None = None) -> Flask:
    app = Flask(__name__)
    store = store or Store(cfg.database_path)
    app.config["WN_CFG"] = cfg
    app.config["WN_STORE"] = store

    @app.get("/healthz")
    def healthz() -> tuple[str, int]:
        return "ok", 200

    @app.post("/webhooks/twilio/sms")
    def twilio_sms() -> Response:
        return handle_inbound(cfg, store, request)

    return app


def handle_inbound(cfg: Config, store: Store, req: Request) -> Response:
    form = {k: str(v) for k, v in req.form.items()}
    from_num = form.get("From", "")
    body = form.get("Body", "")

    # Validate signature when auth token set
    if cfg.twilio_auth_token:
        sig = req.headers.get("X-Twilio-Signature")
        url = req.url
        fwd_proto = req.headers.get("X-Forwarded-Proto")
        if fwd_proto and url.startswith("http://"):
            url = "https://" + url[len("http://") :]
        ok = sms.validate_twilio_signature(
            cfg.twilio_auth_token, sig, url, form
        )
        if not ok:
            log.warning("Invalid Twilio signature from %s", from_num)
            return _twiml("Unauthorized", status=403)

    a = cfg.participant_a_number or ""
    b = cfg.participant_b_number or ""
    known = {a, b} - {""}
    if from_num not in known:
        log.info("Ignoring SMS from unknown number")
        return _twiml("")

    parsed = parse_message(body)
    intent = parsed.intent
    tz = ZoneInfo(cfg.tz)
    now = datetime.now(tz)
    today_d = now.date()
    today = today_d.isoformat()
    yesterday = (today_d - timedelta(days=1)).isoformat()

    reply = ""

    if intent is Intent.OPT_OUT:
        store.set_opt_in(from_num, False)
        reply = sms.msg_opt_out_confirm()
        return _twiml(reply)

    if intent is Intent.OPT_IN:
        store.set_opt_in(from_num, True)
        reply = sms.msg_opt_in_confirm()
        return _twiml(reply)

    if intent is Intent.WORKOUT_YES:
        if from_num == b:
            store.set_opt_in(from_num, True)
        store.set_status(yesterday, from_num, True, source="sms")
        if jobs.maybe_send_partner_update_after_inbound(cfg, store):
            reply = ""
        else:
            reply = sms.msg_got_it()
        return _twiml(reply)

    if intent is Intent.WORKOUT_NO:
        if from_num == b:
            store.set_opt_in(from_num, True)
        store.set_status(yesterday, from_num, False, source="sms")
        if jobs.maybe_send_partner_update_after_inbound(cfg, store):
            reply = ""
        else:
            reply = sms.msg_got_it()
        return _twiml(reply)

    if intent is Intent.TODAY_TRAIN:
        if from_num == b:
            store.set_opt_in(from_num, True)
        store.set_today_intent(today, from_num, "train")
        if jobs.maybe_send_partner_update_after_inbound(cfg, store):
            reply = ""
        else:
            reply = sms.msg_got_it()
        return _twiml(reply)

    if intent is Intent.TODAY_REST:
        if from_num == b:
            store.set_opt_in(from_num, True)
        store.set_today_intent(today, from_num, "rest")
        if jobs.maybe_send_partner_update_after_inbound(cfg, store):
            reply = ""
        else:
            reply = sms.msg_got_it()
        return _twiml(reply)

    if intent is Intent.WEEKLY_COMMIT:
        days = parsed.days
        if days is None or days < 0 or days > 7:
            return _twiml("")
        if from_num == b:
            store.set_opt_in(from_num, True)
        week_of = jobs.commitment_week_of(today_d).isoformat()
        store.set_weekly_goal(from_num, week_of, days)
        reply = sms.msg_weekly_locked(days)
        goal_a = store.get_weekly_goal(a, week_of) if a else None
        goal_b = store.get_weekly_goal(b, week_of) if b else None
        if goal_a is not None and goal_b is not None:
            # SMS each the other's commitment (Winter Rose partner commit)
            sms.send_sms(cfg, a, sms.msg_weekly_partner_commit(goal_a, goal_b))
            if store.is_opted_in(b) or from_num == b:
                sms.send_sms(cfg, b, sms.msg_weekly_partner_commit(goal_b, goal_a))
        return _twiml(reply)

    return _twiml("")


def _twiml(message: str, status: int = 200) -> Response:
    if not message:
        xml = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
    else:
        safe = (
            message.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f"<Response><Message>{safe}</Message></Response>"
        )
    return Response(xml, status=status, mimetype="application/xml")


def serve(cfg: Config) -> None:
    app = create_app(cfg)
    app.run(host=cfg.webhook_host, port=cfg.webhook_port)
