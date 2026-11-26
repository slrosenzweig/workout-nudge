"""Occasional surprise SMS: cheer goals/streaks or nudge when behind."""

from __future__ import annotations

import logging
import random
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from workout_nudge import sms
from workout_nudge.jobs import monday_of
from workout_nudge.store import Store

if TYPE_CHECKING:
    from workout_nudge.config import Config

log = logging.getLogger(__name__)

# Caps per Mon–Sun week
CAP_A = 3
CAP_B = 1
STREAK_MIN = 3
# Midweek weekdays (Wed=2, Thu=3, Fri=4) with zero train days also count as behind
MIDWEEK = {2, 3, 4}


def in_quiet_hours(now: datetime) -> bool:
    """Quiet hours are 9 PM–9 AM local (send only when 09:00 ≤ hour < 21:00)."""
    return now.hour < 9 or now.hour >= 21


def days_left_in_week(today: date, *, trained_today: bool) -> int:
    """Workout days still available: today (if not yet trained) through Sunday."""
    including_today = 7 - today.weekday()
    return including_today - (1 if trained_today else 0)


def train_streak(store: Store, participant: str, today: date) -> int:
    """Consecutive trained days ending today or yesterday."""
    cursor = today
    status = store.get_status(cursor.isoformat(), participant)
    if status is None or status.trained is not True:
        cursor = today - timedelta(days=1)
    n = 0
    while True:
        s = store.get_status(cursor.isoformat(), participant)
        if s is None or s.trained is not True:
            break
        n += 1
        cursor -= timedelta(days=1)
    return n


def pick_hook_a(
    *,
    trained: int,
    goal: int | None,
    streak: int,
    days_left: int,
    today: date,
) -> str | None:
    """Return the highest-priority hook for participant A, or None."""
    if goal is not None and trained >= goal and goal > 0:
        return "hit_goal"
    if goal is not None and trained == goal - 1 and goal > 0:
        return "one_away"
    if streak >= STREAK_MIN:
        return "streak"
    if goal is not None and goal > 0:
        needed = goal - trained
        if needed > 0 and days_left >= 0 and needed >= days_left - 1:
            return "falling_behind"
        if needed > 0 and trained == 0 and today.weekday() in MIDWEEK:
            return "falling_behind"
    return None


def pick_hook_b(*, trained: int, opted_in: bool) -> str | None:
    if not opted_in:
        return None
    if trained > 0:
        return "progress"
    return "quiet"


def can_send(
    *,
    dates_this_week: list[str],
    last_date: str | None,
    today: date,
    cap: int,
    no_back_to_back: bool,
) -> bool:
    today_s = today.isoformat()
    if today_s in dates_this_week:
        return False
    if len(dates_this_week) >= cap:
        return False
    if no_back_to_back and last_date:
        if last_date == (today - timedelta(days=1)).isoformat():
            return False
    return True


def surprise(
    cfg: Config,
    store: Store | None = None,
    *,
    now: datetime | None = None,
    rng: random.Random | None = None,
    roll_a: float | None = None,
    roll_b: float | None = None,
) -> dict:
    """Maybe send a surprise SMS to A (up to 3/week) and/or B (up to 1/week)."""
    store = store or Store(cfg.database_path)
    tz = ZoneInfo(cfg.tz)
    now = now or datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    else:
        now = now.astimezone(tz)
    today = now.date()
    today_s = today.isoformat()
    week_start = monday_of(today)
    week_end = week_start + timedelta(days=6)
    rng = rng or random.Random()

    result: dict = {"day": today_s, "actions": []}

    if in_quiet_hours(now):
        result["actions"].append({"kind": "quiet_hours"})
        log.info("surprise skipped (quiet hours): %s", result)
        return result

    a, b = cfg.require_participants()
    goal_a = store.get_weekly_goal(a, week_start.isoformat())
    trained_a = store.count_train_days(a, week_start.isoformat(), today_s)
    today_status = store.get_status(today_s, a)
    trained_today_a = bool(today_status and today_status.trained is True)
    left = days_left_in_week(today, trained_today=trained_today_a)
    streak = train_streak(store, a, today)

    hook_a = pick_hook_a(
        trained=trained_a,
        goal=goal_a,
        streak=streak,
        days_left=left,
        today=today,
    )
    dates_a = store.surprise_dates(a, week_start.isoformat(), week_end.isoformat())
    last_a = store.last_surprise_date(a)
    p_a = cfg.surprise_p_a
    draw_a = roll_a if roll_a is not None else rng.random()

    if hook_a and can_send(
        dates_this_week=dates_a,
        last_date=last_a,
        today=today,
        cap=CAP_A,
        no_back_to_back=True,
    ) and draw_a < p_a:
        body = sms.msg_surprise_a(
            hook=hook_a,
            trained=trained_a,
            goal=goal_a,
            streak=streak,
            days_left=left,
        )
        sms.send_sms(cfg, a, body)
        store.record_surprise(a, today_s, hook_a)
        result["actions"].append({"to": "A", "kind": "surprise", "hook": hook_a})
    elif hook_a:
        result["actions"].append(
            {"to": "A", "kind": "skipped", "hook": hook_a, "roll": draw_a}
        )
    else:
        result["actions"].append({"to": "A", "kind": "no_hook"})

    trained_b = store.count_train_days(b, week_start.isoformat(), today_s)
    hook_b = pick_hook_b(trained=trained_b, opted_in=store.is_opted_in(b))
    dates_b = store.surprise_dates(b, week_start.isoformat(), week_end.isoformat())
    last_b = store.last_surprise_date(b)
    p_b = cfg.surprise_p_b
    draw_b = roll_b if roll_b is not None else rng.random()

    if hook_b and can_send(
        dates_this_week=dates_b,
        last_date=last_b,
        today=today,
        cap=CAP_B,
        no_back_to_back=False,
    ) and draw_b < p_b:
        body = sms.msg_surprise_b(hook=hook_b, trained=trained_b)
        sms.send_sms(cfg, b, body)
        store.record_surprise(b, today_s, hook_b)
        result["actions"].append({"to": "B", "kind": "surprise", "hook": hook_b})
    elif hook_b:
        result["actions"].append(
            {"to": "B", "kind": "skipped", "hook": hook_b, "roll": draw_b}
        )
    else:
        result["actions"].append({"to": "B", "kind": "no_hook"})

    log.info("surprise complete: %s", result)
    return result
