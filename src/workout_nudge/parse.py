"""Inbound SMS body parsing: YES/NO/STOP/START and variants."""

from __future__ import annotations

from enum import Enum


class Intent(str, Enum):
    OPT_IN = "opt_in"
    OPT_OUT = "opt_out"
    WORKOUT_YES = "workout_yes"
    WORKOUT_NO = "workout_no"
    UNKNOWN = "unknown"


# Exact keyword sets (normalized: strip, lower, collapse whitespace)
_OPT_OUT = frozenset(
    {
        "stop",
        "cancel",
        "quit",
        "optout",
        "opt out",
        "unsubscribe",
        "stopall",
        "stop all",
        "revoke",
        "end",
    }
)

_OPT_IN = frozenset({"start", "unstop"})

_YES = frozenset(
    {
        "yes",
        "yeah",
        "yep",
        "y",
        "did",
        "yup",
        "yea",
    }
)

_NO = frozenset(
    {
        "no",
        "nope",
        "n",
        "didn't",
        "didnt",
        "did not",
        "nah",
    }
)


def normalize_body(body: str | None) -> str:
    if not body:
        return ""
    return " ".join(body.strip().lower().split())


def parse_intent(body: str | None) -> Intent:
    """Classify inbound SMS.

    Exact YES/NO (and variants) are workout answers.
    START/UNSTOP are opt-in only (unless body is exactly a workout YES word —
    YES is workout_yes, which also implies the sender is engaged; callers may
    treat WORKOUT_YES as opt-in for known numbers when appropriate).
    STOP family is opt-out.
    """
    text = normalize_body(body)
    if not text:
        return Intent.UNKNOWN

    # Prefer opt-out over everything
    if text in _OPT_OUT:
        return Intent.OPT_OUT

    # Exact YES/NO as workout answers (before generic START)
    if text in _YES:
        return Intent.WORKOUT_YES
    if text in _NO:
        return Intent.WORKOUT_NO

    if text in _OPT_IN:
        return Intent.OPT_IN

    return Intent.UNKNOWN
