"""Twilio inbound SMS webhook (Flask)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from flask import Flask, Request, Response, request

from workout_nudge.inbound import apply_inbound
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
    sid = form.get("MessageSid") or form.get("SmsSid") or ""

    # Validate signature when auth token set
    if cfg.twilio_auth_token:
        from workout_nudge import sms

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

    if sid and store.inbound_was_processed(sid):
        log.info("Skipping already-processed inbound %s", sid)
        return _twiml("")

    reply = apply_inbound(cfg, store, from_num=from_num, body=body)
    if sid:
        store.mark_inbound_processed(sid, confirm_sent=bool(reply))
    return _twiml(reply)


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
