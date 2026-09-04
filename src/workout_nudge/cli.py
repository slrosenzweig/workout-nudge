"""CLI: nudge | compare | serve."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from workout_nudge.config import Config, load_dotenv
from workout_nudge.jobs import compare, nudge
from workout_nudge.store import Store


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        prog="workout-nudge",
        description="Winter Rose daily workout accountability SMS",
    )
    parser.add_argument(
        "command",
        choices=["nudge", "compare", "serve"],
        help="Job to run",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Debug logging",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    cfg = Config.from_env()

    if args.command == "nudge":
        result = nudge(cfg)
        print(json.dumps(result, indent=2, default=str))
        return 0
    if args.command == "compare":
        result = compare(cfg)
        print(json.dumps(result, indent=2, default=str))
        return 0
    if args.command == "serve":
        from workout_nudge.webhook import serve

        serve(cfg)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
