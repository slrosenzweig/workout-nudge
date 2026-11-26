#!/usr/bin/env python3
"""Fetch and print JSON for a day: readiness, sleep, activity, yesterday workouts.

Usage:
  python scripts/fetch_day.py
  python scripts/fetch_day.py YYYY-MM-DD

Paths and credentials come from the environment (see .env.example),
including OURA_TOKENS_PATH. Do not hardcode secrets.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from workout_nudge import rules  # noqa: E402
from workout_nudge.config import Config, load_dotenv  # noqa: E402
from workout_nudge.oura import OuraClient  # noqa: E402


def compact_qualifying(w: dict) -> dict:
    return {
        "activity": w.get("activity"),
        "source": w.get("source"),
        "intensity": w.get("intensity"),
        "minutes": rules.duration_minutes(w),
        "start": w.get("start_datetime"),
        "end": w.get("end_datetime"),
        "calories": w.get("calories"),
        "label": w.get("label"),
    }


def main() -> int:
    load_dotenv(ROOT / ".env")
    cfg = Config.from_env()
    if not cfg.oura_client_id or not cfg.oura_client_secret:
        print("Set OURA_CLIENT_ID and OURA_CLIENT_SECRET", file=sys.stderr)
        return 1

    tokens_path = cfg.oura_tokens_path
    if not tokens_path.is_absolute():
        tokens_path = ROOT / tokens_path

    if len(sys.argv) > 1:
        try:
            day = date.fromisoformat(sys.argv[1])
        except ValueError:
            print("Usage: python scripts/fetch_day.py [YYYY-MM-DD]", file=sys.stderr)
            return 1
    else:
        day = datetime.now(ZoneInfo(cfg.tz)).date()

    client = OuraClient(
        client_id=cfg.oura_client_id,
        client_secret=cfg.oura_client_secret,
        tokens_path=tokens_path,
    )
    bundle = client.fetch_day_bundle(day)
    y_workouts = bundle.get("yesterday_workouts") or []
    qualifying = [w for w in y_workouts if rules.qualifies_workout(w)]
    out = {
        "day": bundle["day"],
        "yesterday": bundle["yesterday"],
        "readiness": bundle.get("readiness"),
        "sleep": bundle.get("sleep"),
        "activity": bundle.get("activity"),
        "yesterday_workouts": y_workouts,
        "yesterday_trained": rules.yesterday_trained(y_workouts),
        "yesterday_qualifying": [compact_qualifying(w) for w in qualifying],
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
