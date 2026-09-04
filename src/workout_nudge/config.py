"""Environment-based configuration. Never hardcode secrets or PII."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env(key: str, default: str | None = None) -> str | None:
    val = os.environ.get(key)
    if val is None or val.strip() == "":
        return default
    return val.strip()


def _require(key: str) -> str:
    val = _env(key)
    if not val:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return val


@dataclass(frozen=True)
class Config:
    twilio_account_sid: str | None
    twilio_auth_token: str | None
    twilio_messaging_service_sid: str | None
    twilio_from_number: str | None
    oura_client_id: str | None
    oura_client_secret: str | None
    oura_redirect_uri: str
    oura_tokens_path: Path
    participant_a_number: str | None
    participant_b_number: str | None
    tz: str
    database_path: Path
    webhook_host: str
    webhook_port: int

    @classmethod
    def from_env(cls) -> Config:
        tokens = _env("OURA_TOKENS_PATH", "tokens.json") or "tokens.json"
        db = _env("DATABASE_PATH", "workout_nudge.db") or "workout_nudge.db"
        port_s = _env("WEBHOOK_PORT", "8080") or "8080"
        return cls(
            twilio_account_sid=_env("TWILIO_ACCOUNT_SID"),
            twilio_auth_token=_env("TWILIO_AUTH_TOKEN"),
            twilio_messaging_service_sid=_env("TWILIO_MESSAGING_SERVICE_SID"),
            twilio_from_number=_env("TWILIO_FROM_NUMBER"),
            oura_client_id=_env("OURA_CLIENT_ID"),
            oura_client_secret=_env("OURA_CLIENT_SECRET"),
            oura_redirect_uri=_env("OURA_REDIRECT_URI", "http://localhost:8787/callback")
            or "http://localhost:8787/callback",
            oura_tokens_path=Path(tokens),
            participant_a_number=_env("PARTICIPANT_A_NUMBER"),
            participant_b_number=_env("PARTICIPANT_B_NUMBER"),
            tz=_env("TZ", "America/New_York") or "America/New_York",
            database_path=Path(db),
            webhook_host=_env("WEBHOOK_HOST", "0.0.0.0") or "0.0.0.0",
            webhook_port=int(port_s),
        )

    def require_twilio(self) -> tuple[str, str]:
        sid = self.twilio_account_sid
        token = self.twilio_auth_token
        if not sid or not token:
            raise RuntimeError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN are required")
        return sid, token

    def require_participants(self) -> tuple[str, str]:
        a = self.participant_a_number
        b = self.participant_b_number
        if not a or not b:
            raise RuntimeError("PARTICIPANT_A_NUMBER and PARTICIPANT_B_NUMBER are required")
        return a, b


def load_dotenv(path: str | Path = ".env") -> None:
    """Minimal .env loader (no dependency). Does not override existing env."""
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
