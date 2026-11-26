#!/usr/bin/env python3
"""Send the Sunday weekly recap and next-week commitment ask.

Reads Twilio credentials, Messaging Service SID, and participant numbers from
the environment (.env). Do not hardcode phone numbers or SIDs.

Equivalent to: python -m workout_nudge weekly
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from workout_nudge.config import Config, load_dotenv  # noqa: E402
from workout_nudge.jobs import weekly  # noqa: E402


def main() -> int:
    load_dotenv(ROOT / ".env")
    cfg = Config.from_env()
    result = weekly(cfg)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
