#!/usr/bin/env python3
"""Oura OAuth login with localhost callback. Writes tokens.json.

Usage (from repo root, with .env or env vars set):
  python scripts/oauth_login.py

Default callback: http://localhost:8787/callback
"""

from __future__ import annotations

import json
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Allow running without install
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from workout_nudge.config import Config, load_dotenv  # noqa: E402
from workout_nudge.oura import (  # noqa: E402
    authorize_url,
    exchange_code,
    save_tokens,
)


def main() -> int:
    load_dotenv(ROOT / ".env")
    cfg = Config.from_env()
    if not cfg.oura_client_id or not cfg.oura_client_secret:
        print("Set OURA_CLIENT_ID and OURA_CLIENT_SECRET", file=sys.stderr)
        return 1

    redirect = cfg.oura_redirect_uri
    parsed = urlparse(redirect)
    host = parsed.hostname or "localhost"
    port = parsed.port or 8787
    path = parsed.path or "/callback"

    auth = authorize_url(
        client_id=cfg.oura_client_id,
        redirect_uri=redirect,
    )
    print("Open this URL to authorize Oura:")
    print(auth)
    try:
        webbrowser.open(auth)
    except Exception:
        pass

    result: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            u = urlparse(self.path)
            if u.path != path:
                self.send_response(404)
                self.end_headers()
                return
            qs = parse_qs(u.query)
            if "error" in qs:
                result["error"] = qs["error"][0]
                body = b"Authorization failed. You can close this window."
            else:
                code = (qs.get("code") or [None])[0]
                result["code"] = code
                body = b"Authorization OK. You can close this window."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: object) -> None:
            return

    server = HTTPServer((host if host != "localhost" else "127.0.0.1", port), Handler)
    print(f"Listening for callback on {redirect} ...")
    while "code" not in result and "error" not in result:
        server.handle_request()
    server.server_close()

    if result.get("error"):
        print(f"OAuth error: {result['error']}", file=sys.stderr)
        return 1
    code = result.get("code")
    if not code:
        print("No code received", file=sys.stderr)
        return 1

    tokens = exchange_code(
        client_id=cfg.oura_client_id,
        client_secret=cfg.oura_client_secret,
        code=code,
        redirect_uri=redirect,
    )
    out = cfg.oura_tokens_path
    if not out.is_absolute():
        out = ROOT / out
    save_tokens(out, tokens)
    print(f"Wrote tokens to {out}")
    # Do not print secrets
    print(json.dumps({"keys": sorted(tokens.keys())}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
