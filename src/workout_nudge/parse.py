"""Inbound SMS body parsing: YES/NO/TRAIN/REST/STOP/START and variants."""

from __future__ import annotations

from enum import Enum


class Intent(str, Enum):
    OPT_IN = "opt_in"
    OPT_OUT = "opt_out"
    WORKOUT_YES = "workout_yes"
    WORKOUT_NO = "workout_no"
    TODAY_TRAIN = "today_train"
    TODAY_REST = "today_rest"
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


def normalize_body(body: str | None) -> str:
    if not body:
        return ""
    return " ".join(body.strip().lower().split())


def parse_intent(body: str | None) -> Intent:
    """Classify inbound SMS.

    Exact YES/NO (and variants) are yesterday workout answers.
    TRAIN/REST (and variants) are today intent.
    START/UNSTOP are opt-in; STOP family is opt-out.
    """
    text = normalize_body(body)
    if not text:
        return Intent.UNKNOWN

    # Prefer opt-out over everything
    if text in _OPT_OUT:
        return Intent.OPT_OUT

    if text in _YES:
        return Intent.WORKOUT_YES
    if text in _NO:
        return Intent.WORKOUT_NO

    if text in _TRAIN:
        return Intent.TODAY_TRAIN
    if text in _REST:
        return Intent.TODAY_REST

    if text in _OPT_IN:
        return Intent.OPT_IN

    return Intent.UNKNOWN
