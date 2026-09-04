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
from urllib.parse import urlparse

if TYPE_CHECKING:
    from workout_nudge.config import Config

log = logging.getLogger(__name__)


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
    # Twilio: concatenate URL + param keys sorted alphabetically with values
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


# --- Message templates (Winter Rose branded) ---

def msg_train(readiness_score: int) -> str:
    return (
        f"Winter Rose: Recovery looks good today (readiness {readiness_score}). "
        "Should we train this morning? Reply STOP to opt out."
    )


def msg_rest() -> str:
    return "Winter Rose: Recovery is low today. Rest day. Reply STOP to opt out."


def msg_ask_yesterday() -> str:
    return (
        "Winter Rose: Did you work out yesterday? Reply YES or NO. "
        "Reply STOP to opt out."
    )


def msg_partner_comparison(partner_trained: bool) -> str:
    did = "did" if partner_trained else "did not"
    return (
        f"Winter Rose: Your partner {did} train yesterday. "
        "Reply STOP to opt out."
    )


def msg_got_it() -> str:
    return "Winter Rose: Got it."


def msg_partner_no_answer() -> str:
    return (
        "Winter Rose: Your partner hasn't answered yet about yesterday. "
        "Reply STOP to opt out."
    )


def msg_opt_out_confirm() -> str:
    return "Winter Rose: You are opted out. Reply START to opt back in."


def msg_opt_in_confirm() -> str:
    return "Winter Rose: You are opted in. Reply STOP to opt out."
