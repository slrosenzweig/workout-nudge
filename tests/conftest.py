"""Shared test helpers."""

from __future__ import annotations

from pathlib import Path

from workout_nudge.config import Config


A = "+15551110001"
B = "+15551110002"


def make_cfg(tmp_path: Path, **overrides) -> Config:
    kwargs = dict(
        twilio_account_sid="ACtest",
        twilio_auth_token="test-token",
        twilio_messaging_service_sid="",
        twilio_from_number="+15550000000",
        oura_client_id=None,
        oura_client_secret=None,
        oura_redirect_uri="http://localhost:8787/callback",
        oura_tokens_path=tmp_path / "tokens.json",
        participant_a_number=A,
        participant_b_number=B,
        tz="America/New_York",
        database_path=tmp_path / "test.db",
        webhook_host="127.0.0.1",
        webhook_port=8080,
        surprise_p_a=0.30,
        surprise_p_b=0.15,
    )
    kwargs.update(overrides)
    # empty messaging sid should be None-ish for send path; keep as provided
    if kwargs["twilio_messaging_service_sid"] == "":
        kwargs["twilio_messaging_service_sid"] = None
    return Config(**kwargs)
