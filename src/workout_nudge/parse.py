"""Inbound SMS body parsing: YES/NO/TRAIN/REST/STOP/START, weekly commit 0–7."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Intent(str, Enum):
    OPT_IN = "opt_in"
    OPT_OUT = "opt_out"
    WORKOUT_YES = "workout_yes"
    WORKOUT_NO = "workout_no"
    TODAY_TRAIN = "today_train"
    TODAY_REST = "today_rest"
    WEEKLY_COMMIT = "weekly_commit"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ParseResult:
    intent: Intent
    days: int | None = None


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

_TRAIN = frozenset(
    {
        "train",
        "training",
        "train day",
        "train today",
        "training day",
        "training today",
    }
)

_REST = frozenset(
    {
        "rest",
        "resting",
        "rest day",
        "rest today",
        "resting day",
        "resting today",
    }
)

# Lone 0–7, or phrases like "4 days", "I'll do 5", "commit 3"
_WEEKLY_PATTERNS = (
    re.compile(r"^([0-7])$"),
    re.compile(r"^([0-7])\s*days?$"),
    re.compile(r"^i'?ll\s+do\s+([0-7])(?:\s*days?)?$"),
    re.compile(r"^commit\s+([0-7])(?:\s*days?)?$"),
    re.compile(r"^(?:do|doing)\s+([0-7])(?:\s*days?)?$"),
)


def normalize_body(body: str | None) -> str:
    if not body:
        return ""
    return " ".join(body.strip().lower().split())


def _parse_weekly_days(text: str) -> int | None:
    for pat in _WEEKLY_PATTERNS:
        m = pat.match(text)
        if m:
            return int(m.group(1))
    return None


def parse_message(body: str | None) -> ParseResult:
    """Classify inbound SMS; WEEKLY_COMMIT includes days 0–7."""
    text = normalize_body(body)
    if not text:
        return ParseResult(Intent.UNKNOWN)

    # Prefer opt-out over everything
    if text in _OPT_OUT:
        return ParseResult(Intent.OPT_OUT)

    if text in _YES:
        return ParseResult(Intent.WORKOUT_YES)
    if text in _NO:
        return ParseResult(Intent.WORKOUT_NO)

    if text in _TRAIN:
        return ParseResult(Intent.TODAY_TRAIN)
    if text in _REST:
        return ParseResult(Intent.TODAY_REST)

    if text in _OPT_IN:
        return ParseResult(Intent.OPT_IN)

    days = _parse_weekly_days(text)
    if days is not None:
        return ParseResult(Intent.WEEKLY_COMMIT, days=days)

    return ParseResult(Intent.UNKNOWN)


def parse_intent(body: str | None) -> Intent:
    """Classify inbound SMS (intent only; see parse_message for weekly days).

    Exact YES/NO (and variants) are yesterday workout answers.
    TRAIN/REST (and variants) are today intent.
    START/UNSTOP are opt-in; STOP family is opt-out.
    Lone 0–7 / "N days" / "I'll do N" / "commit N" → WEEKLY_COMMIT.
    """
    return parse_message(body).intent
