"""Oura Ring OAuth + v2 usercollection API client.

Refresh tokens are SINGLE USE — always persist the new refresh_token after refresh.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

TOKEN_URL = "https://api.ouraring.com/oauth/token"
AUTHORIZE_URL = "https://cloud.ouraring.com/oauth/authorize"
API_BASE = "https://api.ouraring.com/v2/usercollection"
SCOPES = "daily workout session personal"


class OuraError(RuntimeError):
    pass


def load_tokens(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise OuraError(f"Oura tokens file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_tokens(path: Path, tokens: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(tokens, indent=2) + "\n", encoding="utf-8")
    log.info("Persisted Oura tokens to %s", path)


def exchange_code(
    *,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
) -> dict[str, Any]:
    data = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode("utf-8")
    req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise OuraError(f"Token exchange failed: {e.code} {body}") from e


def refresh_access_token(
    *,
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> dict[str, Any]:
    """Refresh; caller MUST persist the new refresh_token (single-use)."""
    data = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode("utf-8")
    req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise OuraError(f"Token refresh failed: {e.code} {body}") from e


class OuraClient:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        tokens_path: Path,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.tokens_path = tokens_path
        self._tokens = load_tokens(tokens_path)

    @property
    def access_token(self) -> str:
        token = self._tokens.get("access_token")
        if not token:
            raise OuraError("No access_token in tokens file")
        return token

    def ensure_fresh(self) -> None:
        """Refresh if we only have refresh_token or on demand before API calls.

        Always persists new tokens after a successful refresh.
        """
        refresh = self._tokens.get("refresh_token")
        if not refresh:
            # Rely on existing access_token
            return
        # Proactively refresh when no access_token
        if not self._tokens.get("access_token"):
            self._do_refresh()

    def _do_refresh(self) -> None:
        refresh = self._tokens.get("refresh_token")
        if not refresh:
            raise OuraError("No refresh_token available")
        new_tokens = refresh_access_token(
            client_id=self.client_id,
            client_secret=self.client_secret,
            refresh_token=refresh,
        )
        # Merge: keep any extra fields; new refresh_token is single-use
        self._tokens = {**self._tokens, **new_tokens}
        save_tokens(self.tokens_path, self._tokens)

    def _request(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        qs = urllib.parse.urlencode(params)
        url = f"{API_BASE}/{path}?{qs}"
        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", f"Bearer {self.access_token}")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 401:
                log.info("Oura 401 — refreshing token and retrying")
                self._do_refresh()
                req2 = urllib.request.Request(url, method="GET")
                req2.add_header("Authorization", f"Bearer {self.access_token}")
                with urllib.request.urlopen(req2, timeout=30) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            body = e.read().decode("utf-8", errors="replace")
            raise OuraError(f"Oura API {path} failed: {e.code} {body}") from e

    def get_collection(
        self, name: str, start_date: date, end_date: date
    ) -> list[dict[str, Any]]:
        data = self._request(
            name,
            {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        )
        return list(data.get("data") or [])

    def fetch_day_bundle(self, today: date) -> dict[str, Any]:
        """Fetch readiness/sleep/activity for today; workouts yesterday..today."""
        yesterday = today - timedelta(days=1)
        readiness = self.get_collection("daily_readiness", today, today)
        sleep = self.get_collection("daily_sleep", today, today)
        activity = self.get_collection("daily_activity", today, today)
        workouts = self.get_collection("workout", yesterday, today)

        # Filter workouts whose calendar day (local start) == yesterday
        yesterday_workouts = [
            w
            for w in workouts
            if _workout_day(w) == yesterday.isoformat()
        ]

        return {
            "day": today.isoformat(),
            "yesterday": yesterday.isoformat(),
            "readiness": readiness[0] if readiness else None,
            "sleep": sleep[0] if sleep else None,
            "activity": activity[0] if activity else None,
            "yesterday_workouts": yesterday_workouts,
            "all_workouts_span": workouts,
        }


def _workout_day(w: dict[str, Any]) -> str | None:
    """Best-effort day string YYYY-MM-DD from workout."""
    if w.get("day"):
        return str(w["day"])[:10]
    start = w.get("start_datetime")
    if not start:
        return None
    # ISO may include timezone; take date portion
    return str(start)[:10]


def authorize_url(*, client_id: str, redirect_uri: str, state: str = "workout-nudge") -> str:
    qs = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "state": state,
        }
    )
    return f"{AUTHORIZE_URL}?{qs}"
