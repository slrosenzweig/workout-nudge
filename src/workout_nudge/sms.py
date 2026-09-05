"""Twilio SMS send via stdlib urllib."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from workout_nudge.config import Config

log = logging.getLogger(__name__)

BRAND = "Sarah"


def send_sms(cfg: Config, to: str, body: str) -> dict:
    """POST Messages.json. Prefer MessagingServiceSid when set."""
    account_sid, auth_token = cfg.require_twilio()
    url = (
        f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    )
    data: dict[str, str] = {"To": to, "Body": body}
    if cfg.twilio_messaging_service_sid:
        data["MessagingServiceSid"] = cfg.twilio_messaging_service_sid
    elif cfg.twilio_from_number:
        data["From"] = cfg.twilio_from_number
    else:
        raise RuntimeError(
            "Set TWILIO_MESSAGING_SERVICE_SID or TWILIO_FROM_NUMBER"
        )

    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=encoded, method="POST")
    credentials = base64.b64encode(
        f"{account_sid}:{auth_token}".encode("utf-8")
    ).decode("ascii")
    req.add_header("Authorization", f"Basic {credentials}")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            log.info("SMS sent to %s sid=%s", to, payload.get("sid"))
            return payload
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        log.error("Twilio send failed %s: %s", e.code, err_body)
        raise RuntimeError(f"Twilio send failed: {e.code} {err_body}") from e


def validate_twilio_signature(
    auth_token: str,
    signature: str | None,
    url: str,
    params: dict[str, str],
) -> bool:
    """Validate X-Twilio-Signature (HMAC-SHA1 of url + sorted params)."""
    if not signature:
        return False
    s = url
    for key in sorted(params.keys()):
        s += key + params[key]
    digest = hmac.new(
        auth_token.encode("utf-8"),
        s.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)


# --- Message templates (Sarah branded) ---


def msg_sync_ring() -> str:
    return (
        f"{BRAND}: Good morning — open Oura and sync your ring so we can pull "
        "today’s scores. Reply STOP to opt out."
    )


def msg_report_a(
    *,
    readiness_score: int | None,
    activity_score: int | None,
    today_intent: str,
    yesterday_trained: bool | None,
    ask_yesterday: bool,
) -> str:
    """One report SMS for participant A."""
    r = str(readiness_score) if readiness_score is not None else "n/a"
    a = str(activity_score) if activity_score is not None else "n/a"
    intent_word = "train" if today_intent == "train" else "rest"
    parts = [
        f"{BRAND}: Readiness {r}, activity {a}. Today: {intent_word}.",
    ]
    if ask_yesterday:
        parts.append("Did you work out yesterday? Reply YES or NO.")
    elif yesterday_trained is True:
        parts.append("Yesterday: trained.")
    elif yesterday_trained is False:
        parts.append("Yesterday: rest.")
    parts.append("Reply STOP to opt out.")
    return " ".join(parts)


def msg_ask_b() -> str:
    """Ask B for yesterday YES/NO and today TRAIN/REST."""
    return (
        f"{BRAND}: Did you work out yesterday? Reply YES or NO. "
        "For today, reply TRAIN or REST. Reply STOP to opt out."
    )


def msg_ask_yesterday() -> str:
    return (
        f"{BRAND}: Did you work out yesterday? Reply YES or NO. "
        "Reply STOP to opt out."
    )


def msg_ask_today_intent() -> str:
    return (
        f"{BRAND}: For today, reply TRAIN or REST. Reply STOP to opt out."
    )


def msg_ask_incomplete(*, need_yesterday: bool, need_intent: bool) -> str:
    bits: list[str] = []
    if need_yesterday:
        bits.append("Did you work out yesterday? Reply YES or NO.")
    if need_intent:
        bits.append("For today, reply TRAIN or REST.")
    if not bits:
        return f"{BRAND}: Got it."
    return f"{BRAND}: {' '.join(bits)} Reply STOP to opt out."


def msg_partner_update(
    *,
    partner_trained_yesterday: bool,
    partner_today_intent: str,
) -> str:
    y = "trained" if partner_trained_yesterday else "rested"
    t = "train" if partner_today_intent == "train" else "rest"
    return (
        f"{BRAND}: Your partner {y} yesterday and plans to {t} today. "
        "Reply STOP to opt out."
    )


def msg_partner_no_update() -> str:
    return (
        f"{BRAND}: Your partner hasn’t updated yet. Reply STOP to opt out."
    )


def msg_got_it() -> str:
    return f"{BRAND}: Got it."


def msg_opt_out_confirm() -> str:
    return f"{BRAND}: You are opted out. Reply START to opt back in."


def msg_opt_in_confirm() -> str:
    return f"{BRAND}: You are opted in. Reply STOP to opt out."


# Deprecated aliases kept for any leftover callers
def msg_train(readiness_score: int) -> str:
    return (
        f"{BRAND}: Recovery looks good today (readiness {readiness_score}). "
        "Today: train. Reply STOP to opt out."
    )


def msg_rest() -> str:
    return f"{BRAND}: Recovery is low today. Today: rest. Reply STOP to opt out."


def msg_partner_comparison(partner_trained: bool) -> str:
    return msg_partner_update(
        partner_trained_yesterday=partner_trained,
        partner_today_intent="rest",
    )


def msg_partner_no_answer() -> str:
    return msg_partner_no_update()
