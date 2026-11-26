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
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from workout_nudge.config import Config

log = logging.getLogger(__name__)

BRAND = "Frank the Trainer"


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


def list_inbound_messages(
    cfg: Config,
    *,
    sent_after: datetime,
) -> list[dict[str, Any]]:
    """List inbound Twilio messages on or after sent_after (local or aware)."""
    account_sid, auth_token = cfg.require_twilio()
    # DateSent>= is midnight GMT of that date; filter more precisely in Python.
    date_param = sent_after.date().isoformat()
    url: str | None = (
        f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    )
    params = {"PageSize": "100", "DateSent>=": date_param}
    credentials = base64.b64encode(
        f"{account_sid}:{auth_token}".encode("utf-8")
    ).decode("ascii")
    out: list[dict[str, Any]] = []
    first = True
    while url:
        if first:
            url = url + "?" + urllib.parse.urlencode(params)
            first = False
        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", f"Basic {credentials}")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            log.error("Twilio list failed %s: %s", e.code, err_body)
            raise RuntimeError(f"Twilio list failed: {e.code} {err_body}") from e
        for m in payload.get("messages") or []:
            direction = (m.get("direction") or "").lower()
            if direction and direction != "inbound":
                continue
            created = m.get("date_created") or m.get("date_sent") or ""
            when: datetime | None = None
            if created:
                try:
                    when = parsedate_to_datetime(created)
                except (TypeError, ValueError, IndexError):
                    try:
                        when = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                    except ValueError:
                        when = None
            if when is not None:
                after = sent_after
                if when.tzinfo is None and after.tzinfo is not None:
                    when = when.replace(tzinfo=after.tzinfo)
                elif when.tzinfo is not None and after.tzinfo is None:
                    after = after.replace(tzinfo=when.tzinfo)
                if when < after:
                    continue
            out.append(
                {
                    "sid": m.get("sid"),
                    "from": m.get("from") or m.get("from_"),
                    "to": m.get("to"),
                    "body": m.get("body"),
                    "date_created": created,
                    "direction": direction or "inbound",
                }
            )
        url = payload.get("next_page_uri")
        if url and url.startswith("/"):
            url = "https://api.twilio.com" + url
    return out


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


# --- Message templates (Frank the Trainer branded) ---


def msg_sync_ring() -> str:
    return (
        f"{BRAND}: Good morning — open Oura and sync your ring so we can pull "
        "today’s scores. Reply STOP to opt out."
    )


def scoreboard_fragment(days: int, goal: int | None) -> str:
    """Closed-week scoreboard sentence (no brand prefix)."""
    unit = "day" if days == 1 else "days"
    if goal is None:
        return f"Last week you trained {days} {unit} — no goal set."
    if days >= goal:
        return f"Last week you trained {days}/{goal} days — goal met."
    return f"Last week you trained {days}/{goal} days — missed."


def msg_report_a(
    *,
    readiness_score: int | None,
    activity_score: int | None,
    today_intent: str,
    yesterday_trained: bool | None,
    ask_yesterday: bool,
    scoreboard: str | None = None,
    weekly_progress: str | None = None,
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
    if weekly_progress:
        parts.append(weekly_progress)
    if scoreboard:
        parts.append(scoreboard)
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


def msg_weekly_recap(
    *,
    my_days: int,
    my_goal: int | None,
    partner_days: int | None = None,
    partner_goal: int | None = None,
    include_partner: bool = False,
) -> str:
    """Sunday recap: your days vs goal, and partner's if known."""
    if my_goal is None:
        mine = f"you trained {my_days} day{'s' if my_days != 1 else ''} — no goal set"
    elif my_days >= my_goal:
        mine = f"you trained {my_days}/{my_goal} days — goal met"
    else:
        mine = f"you trained {my_days}/{my_goal} days — missed"

    parts = [f"{BRAND}: This week {mine}."]
    if include_partner:
        if partner_goal is None and partner_days is None:
            parts.append("Partner: no update.")
        elif partner_goal is None:
            pd = partner_days if partner_days is not None else 0
            parts.append(
                f"Partner trained {pd} day{'s' if pd != 1 else ''} (no goal)."
            )
        else:
            pd = partner_days if partner_days is not None else 0
            if pd >= partner_goal:
                parts.append(f"Partner: {pd}/{partner_goal} — met.")
            else:
                parts.append(f"Partner: {pd}/{partner_goal} — missed.")
    parts.append("Reply STOP to opt out.")
    return " ".join(parts)


def msg_weekly_ask() -> str:
    return (
        f"{BRAND}: New week — how many days will you commit to working out "
        "(Mon–Sun)? Reply with a number 0–7. Reply STOP to opt out."
    )


def msg_weekly_locked(n: int) -> str:
    return (
        f"{BRAND}: Locked in — {n} day{'s' if n != 1 else ''} this week. "
        "Reply STOP to opt out."
    )


def msg_weekly_partner_commit(my_n: int, their_n: int) -> str:
    return (
        f"{BRAND}: You’re in for {my_n}; your partner committed to {their_n} "
        "this week. Reply STOP to opt out."
    )


def msg_surprise_a(
    *,
    hook: str,
    trained: int,
    goal: int | None,
    streak: int,
    days_left: int,
) -> str:
    """Surprise text for participant A. Never invents specific workouts."""
    if hook == "hit_goal" and goal is not None:
        body = (
            f"That’s the week — you already hit your {goal}-day goal. Nice work."
        )
    elif hook == "one_away" and goal is not None:
        body = f"You’re one workout away from your {goal}-day goal. You’ve got this."
    elif hook == "streak":
        body = f"That’s a {streak}-day streak. Keep the fire going."
    elif hook == "falling_behind" and goal is not None:
        left = "day" if days_left == 1 else "days"
        body = (
            f"You’re at {trained} of {goal} with {days_left} {left} left — "
            "time to get after it."
        )
    else:
        body = "Checking in — keep showing up this week."
    return f"{BRAND}: {body} Reply STOP to opt out."


def msg_surprise_b(*, hook: str, trained: int) -> str:
    """Surprise text for participant B. Does not mention participant A’s details."""
    if hook == "progress":
        unit = "day" if trained == 1 else "days"
        body = f"Nice progress this week — {trained} workout {unit} on the board. Keep it up."
    else:
        body = (
            "Just a nudge — reply YES or NO for yesterday and TRAIN or REST "
            "for today when you’re ready."
        )
    return f"{BRAND}: {body} Reply STOP to opt out."

