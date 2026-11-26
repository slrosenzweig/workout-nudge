#!/usr/bin/env python3
"""List Oura workouts for a date range (defaults to today).

Usage:
  python scripts/fetch_workouts.py
  python scripts/fetch_workouts.py YYYY-MM-DD
  python scripts/fetch_workouts.py YYYY-MM-DD YYYY-MM-DD

Credentials and OURA_TOKENS_PATH come from the environment. Never hardcode paths
to token files that contain secrets.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from workout_nudge.config import Config, load_dotenv  # noqa: E402
from workout_nudge.oura import OuraClient  # noqa: E402


def main() -> int:
    load_dotenv(ROOT / ".env")
    cfg = Config.from_env()
    if not cfg.oura_client_id or not cfg.oura_client_secret:
        print("Set OURA_CLIENT_ID and OURA_CLIENT_SECRET", file=sys.stderr)
        return 1

    tokens_path = cfg.oura_tokens_path
    if not tokens_path.is_absolute():
        tokens_path = ROOT / tokens_path

    today = datetime.now(ZoneInfo(cfg.tz)).date()
    try:
        start = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else today
        end = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else start
    except ValueError:
        print(
            "Usage: python scripts/fetch_workouts.py [START_DATE] [END_DATE]",
            file=sys.stderr,
        )
        return 1

    client = OuraClient(
        client_id=cfg.oura_client_id,
        client_secret=cfg.oura_client_secret,
        tokens_path=tokens_path,
    )
    data = client.get_collection("workout", start, end)
    print(json.dumps({"start": start.isoformat(), "end": end.isoformat(), "data": data}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
